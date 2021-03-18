#!/usr/bin/env python3
#
# ELL build checker
#
# Tedd Ho-Jeong An (tedd.an@intel.com)
import os
import sys
import argparse
import logging
import subprocess
import configparser
import git
import datetime
import smtplib
import email.utils
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = None
config = None

src_dir = None
sha_file_path = None

EMAIL_SUBJECT = '''[Intel - Internal] ELL Check Build Result: {result} - {date}'''
EMAIL_MESSAGE = '''This is automated email and please do not reply to this email!

ELL Build Test Report:

Result: {result}

Repo: {repo_url}:{repo_branch}

Last Commit:
-----------------------------------------------------------------------
{top_commit_log}
-----------------------------------------------------------------------

Output:
--------------
{output}

---
Regards,
Linux Bluetooth
'''

def send_email(config, subject, message):
    receivers = []
    if 'only-maintainers' in config and config['only-maintainers'] == 'yes':
        # Send only to the addresses in the 'maintainers'
        maintainers = "".join(config['maintainers'].splitlines()).split(",")
        receivers.extend(maintainers)
    else:
        # Send to default-to address and submitter
        receivers.append(config['default-to'])

    msg = MIMEMultipart()
    msg['From'] = config['user']
    msg['To'] = ",".join(receivers)
    msg['Subject'] = subject
    msg.attach(MIMEText(message, 'plain'))
    logger.debug("Email Message: \n{}".format(msg))

    if 'EMAIL_TOKEN' not in os.environ:
        logger.error("Unable to find EMAIL Token. Cannot send email")
        return -1

    try:
        session = smtplib.SMTP(config['server'], int(config['port']))
        session.ehlo()
        if 'starttls' not in config or config['starttls'] == 'yes':
            session.starttls()
        session.ehlo()
        session.login(config['user'], os.environ['EMAIL_TOKEN'])
        session.sendmail(config['user'], receivers, msg.as_string())
        logger.info("Successfully sent email")
    except Exception as e:
        logger.error("Exception: {}".format(e))
    finally:
        session.quit()
    logger.info("Sending email done")

def generate_date():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def report_result(email_config, result, repo_url, branch, commit_log, output):
    subject = EMAIL_SUBJECT.format(result=result, date=generate_date())
    message = EMAIL_MESSAGE.format(result=result,
                                   repo_url=repo_url,
                                   repo_branch=branch,
                                   top_commit_log=commit_log,
                                   output=output)
    logger.info("EMAIL MESSAGE:\n{}\n\n{}".format(subject, message))

    send_email(email_config, subject, message)

def parse_config(config_file):
    config = configparser.ConfigParser()
    config_full_path = os.path.abspath(config_file)
    if not os.path.exists(config_full_path):
        logger.error("Unable to find config file. Skip sending report")
        return None

    logger.info("Loading config file: %s" % config_full_path)
    config.read(config_full_path)

    # Display current config settings
    for section in config.sections():
        logger.debug("[%s]" % section)
        for (key, val) in config.items(section):
            logger.debug("   %s : %s" % (key, val))

    return config

def run_cmd(*args, cwd=None):
    """ Run command and return return code, stdout and stderr """

    cmd = []
    cmd.extend(args)
    cmd_str = "{}".format(" ".join(str(w) for w in cmd))
    logger.info("CMD: %s" % cmd_str)

    stdout = ""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1, cwd=cwd,
                                stderr=subprocess.PIPE, universal_newlines=True)
    except OSError as e:
        logger.error("ERROR: failed to run cmd: %s" % e)
        return (-1, None, None)

    for line in proc.stdout:
        logger.debug(line.rstrip('\n'))
        stdout += line

    # stdout is consumed in previous line. so, communicate() returns empty
    _ignore, stderr = proc.communicate()

    logger.debug(">> STDERR\n{}".format(stderr))

    return (proc.returncode, stdout, stderr)

def read_sha_from_file(sha_file):
    sha = None
    with open(sha_file, 'r') as f:
        sha = f.readline()
    return sha

def write_sha_to_file(sha_file, new_sha):
    with open(sha_file, 'w') as f:
        f.write(new_sha)

def compare_sha(sha1, sha2):
    if (sha1.rstrip() == sha2.rstrip()):
        return True
    return False

def get_repo_info(src_path):
    repo = git.Repo.init(path=src_path)
    if not repo:
        logger.error("Unable to init Git Repo from: %s" % src_path)
        return (None, None, None)

    repo_url = repo.remote().url
    branch = repo.active_branch.name
    sha = repo.head.commit.hexsha

    logger.info("Repo Information:")
    logger.info("   Repo URL:  %s" % repo_url)
    logger.info("   Branch:    %s" % branch)
    logger.info("   HEAD SHA:  %s" % sha)

    return (repo_url, branch, sha)

def run_checkbuild(src_dir):
    (ret, stdout, stderr) = run_cmd("./bootstrap-configure",
                                    cwd=src_dir)
    if ret:
        # add_failure(stderr)
        logger.error("configure failed")
        logger.error(stderr)
        return (1, stderr)

    (ret, stdout, stderr) = run_cmd("make", cwd=src_dir)
    if ret:
        # add_failure(stderr)
        logger.error("make failed")
        logger.error(stderr)
        return (2, stderr)

    return (0, None)

def commit_file(filename):
    logger.debug("Commit file")
    (ret, stdout, stderr) = run_cmd("git", "commit", "-m",
                                    "\"Auto Commit: Update new commit id\"",
                                    filename,
                                    cwd=os.path.curdir)
    if ret:
        logger.error("Unable to git commit: %s\n%s" % (filename, stderr))
        return False
    logger.debug("output:\n%s" % stdout)

    (ret, stdout, stderr) = run_cmd("git", "push", "upstream", "main",
                                    cwd=os.path.curdir)
    if ret:
        logger.error("Unable to git push:\n%s" % stderr)
        return False
    logger.debug("output:\n%s" % stdout)

    return True

def init_logging(verbose):
    global logger

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    if verbose:
        logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s:%(levelname)-8s:%(message)s')
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    logger.info("Logger is initialized: level=%s",
                 logging.getLevelName(logger.getEffectiveLevel()))

def parse_args():
    parser = argparse.ArgumentParser(description="Run buildcheck for ELL")
    parser.add_argument('-c', '--config-file', default='config.ini',
                        help='Email configuration file')
    parser.add_argument('-s', '--src', default='./ell',
                        help="Path to the source folder of ELL")
    parser.add_argument('-f', '--head-sha-file', default='./head.sha',
                        help='Last checked SHA in file')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Display debugging info')
    parser.add_argument('-e', '--email-on-success', action='store_true',
                        help='Send email on success as well', default=False)

    return parser.parse_args()

def main():
    global src_dir
    global sha_file_path

    args = parse_args()

    init_logging(args.verbose)

    src_dir = os.path.abspath(args.src)
    logger.debug("SRC DIR: %s" % src_dir)
    sha_file_path = os.path.abspath(args.head_sha_file)
    logger.debug("SHA FILE: %s" % sha_file_path)

    config = parse_config(args.config_file)
    if not config:
        logger.error("Unable to read email configuration")
        sys.exit(1)

    # Check parameters
    if not os.path.exists(sha_file_path):
        logger.error("Unable to find Head SHA file from: %s" % sha_file_path)
        sys.exit(1)

    if not os.path.exists(src_dir):
        logger.error("Unable to find source from: %s" % src_dir)
        sys.exit(1)

    # Read last tested SHA from file
    last_known_sha = read_sha_from_file(sha_file_path)
    if not last_known_sha:
        logger.error("Unable to read HEAD SHA from file: %s" % sha_file_path)
        sys.exit(1)
    logger.info("Last known HEAD SHA: %s" % last_known_sha)

    # Read Repo Information
    (src_repo, src_branch, src_head_sha) = get_repo_info(src_dir)

    # Compare  HEAD SHA
    if compare_sha(src_head_sha, last_known_sha):
        logger.info("Exit Success. No new commit found from the last run")
        sys.exit(0)

    # Get the most recent log
    (ret, top_log, stderr) = run_cmd("git", "log", "-1", "--no-decorate",
                                    cwd=src_dir)
    if ret:
        logger.error("Unable to get the first commit log. Use commit id")
        top_log = src_head_sha
    logger.debug("HEAD Log:\n%s" % top_log)

    # Update new SHA to file.
    if write_sha_to_file(sha_file_path, src_head_sha):
        logger.error("Unable to write new HEAD SHA to file")
        sys.exit(1)

    # Commit file to repo
    if not commit_file(sha_file_path):
        logger.error("Unable to commit file: %s" % sha_file_path)

    # Run test.
    try:
        (ret, output_err) = run_checkbuild(src_dir)
    except BaseException as e:
        logger.error("Exception: %s" % e)
        raise
    logger.info("Checkbuild status=%d" % ret)

    if ret == 0:
        logger.info("Build Success. Done")
        if args.email_on_success:
            report_result(config['email'], "SUCCESS", src_repo, src_branch,
                          top_log, "success")
        sys.exit(ret)

    # Build Failed. Report to the people
    logger.error("Checkbuild failed. Send out notification")

    report_result(config['email'], "FAIL", src_repo, src_branch,
                  top_log, output_err)

    sys.exit(ret)

if __name__ == "__main__":
    main()

