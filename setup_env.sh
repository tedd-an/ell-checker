#!/bin/bash

echo "Setup Env script"

export DEBIAN_FRONTEND=noninteractive
sudo locale-gen en_US.UTF-8
export LANG=en_US.UTF-8
export LANGUAGE=en_US:en
export LC_ALL=en_US.UTF-8

echo "Install packages"

sudo apt-get clean && sudo apt-get -y update
sudo apt-get install --no-install-recommends -y \
        autoconf        \
        automake        \
        build-essential \
        libglib2.0-dev  \
        libtool         \
        openssl         \
        python3         \
        python3-pip

echo "Install Python Packages"

sudo pip3 install --no-cache-dir setuptools
sudo pip3 install --no-cache-dir \
        gitpython       \
        pygithub

echo "Setup Environment"

git config user.name "BlueZ Test Bot"
git config user.email "bluez.test.bot@gmail.com"
git config http.sslVerify false

upstream_repo="https://${GITHUB_ACTOR}:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git remote add upstream "${upstream_repo}"
