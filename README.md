# ell-checker
ELL Checker

Ell-Checker builds ELL to check the integrity of the build.
It runs the test if there is new commit in the ELL repository after comparing the HEAD with the previous commit id saved in head.sha file.

If the build complets with any error, it sends email to the list of people described in the config.ini file with error details, otherwise do nothing.
