#!/bin/sh
# Shadow Reader launcher. Works on any Linux with POSIX sh.
# If Python 3 or Poppler's pdftotext is missing, it offers to install them with
# whichever package manager this system has (apt, dnf, yum, pacman, zypper, apk,
# xbps, emerge). It never installs anything without asking first.
set -eu
cd "$(dirname "$0")"

PM=""
PRIV=""
CMD1=""
CMD2=""

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    echo python3
    return 0
  fi
  if command -v python >/dev/null 2>&1 &&
    python -c 'import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
    echo python
    return 0
  fi
  return 1
}

detect_pm() {
  for candidate in apt-get dnf yum pacman zypper apk xbps-install emerge; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PM=$candidate
      return 0
    fi
  done
  return 1
}

# Package names differ by distribution. $1 is "python" or "poppler".
package_name() {
  case "$PM:$1" in
    apt-get:python | dnf:python | yum:python | zypper:python | apk:python | xbps-install:python) echo python3 ;;
    pacman:python) echo python ;;
    emerge:python) echo dev-lang/python ;;
    apt-get:poppler | dnf:poppler | yum:poppler | apk:poppler) echo poppler-utils ;;
    zypper:poppler) echo poppler-tools ;;
    pacman:poppler | xbps-install:poppler) echo poppler ;;
    emerge:poppler) echo app-text/poppler ;;
  esac
}

# Sets CMD1 (and CMD2 when a second step is needed) for installing the packages in $*.
build_commands() {
  CMD1=""
  CMD2=""
  case "$PM" in
    apt-get)
      CMD1="apt-get update"
      CMD2="apt-get install -y $*"
      ;;
    dnf) CMD1="dnf install -y $*" ;;
    yum) CMD1="yum install -y $*" ;;
    pacman) CMD1="pacman -S --needed --noconfirm $*" ;;
    zypper) CMD1="zypper --non-interactive install $*" ;;
    apk) CMD1="apk add $*" ;;
    xbps-install) CMD1="xbps-install -Sy $*" ;;
    emerge) CMD1="emerge --ask=n $*" ;;
  esac
}

detect_privilege() {
  if [ "$(id -u)" = "0" ]; then
    PRIV=""
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    PRIV="sudo"
    return 0
  fi
  if command -v doas >/dev/null 2>&1; then
    PRIV="doas"
    return 0
  fi
  return 1
}

# Show the command the way the user would type it.
display_commands() {
  if [ -n "$CMD2" ]; then
    echo "  ${PRIV:+$PRIV }$CMD1 && ${PRIV:+$PRIV }$CMD2"
  else
    echo "  ${PRIV:+$PRIV }$CMD1"
  fi
}

# Offers to install what is missing ($1 = python and/or poppler words).
# Returns 0 only if the install command ran and succeeded.
offer_install() {
  wanted="$1"
  if ! detect_pm; then
    echo "I could not recognise this system's package manager."
    case "$wanted" in
      *python*) echo "Please install Python 3 using your distribution's package manager." ;;
    esac
    case "$wanted" in
      *poppler*) echo "Please install Poppler (the package that provides 'pdftotext'; usually named poppler-utils, poppler-tools or poppler)." ;;
    esac
    return 1
  fi

  packages=""
  for item in $wanted; do
    packages="$packages $(package_name "$item")"
  done
  packages=${packages# }

  if detect_privilege; then
    :
  else
    PRIV=""
    build_commands "$packages"
    echo "No sudo or doas was found. To install it, run this as an administrator (root):"
    display_commands
    return 1
  fi
  build_commands "$packages"
  echo "To install it, this command would run:"
  display_commands

  if [ ! -t 0 ]; then
    echo "This is not an interactive terminal, so nothing was installed. Run the command above yourself."
    return 1
  fi

  printf "Run it now? [y/N] "
  answer=""
  read -r answer || answer=""
  case "$answer" in
    y | Y | yes | YES) ;;
    *) return 1 ;;
  esac

  # $PRIV and the commands are plain words defined above, so splitting is intended.
  # shellcheck disable=SC2086
  $PRIV $CMD1 || return 1
  if [ -n "$CMD2" ]; then
    # shellcheck disable=SC2086
    $PRIV $CMD2 || return 1
  fi
  return 0
}

PYTHON=$(find_python) || PYTHON=""

missing=""
[ -n "$PYTHON" ] || missing="python"
command -v pdftotext >/dev/null 2>&1 || missing="$missing poppler"
missing=${missing# }

if [ -n "$missing" ]; then
  case "$missing" in
    *python*) echo "Shadow Reader needs Python 3 to run its local server." ;;
  esac
  case "$missing" in
    *poppler*) echo "Shadow Reader needs Poppler's pdftotext command to turn PDF pages into flowing text." ;;
  esac
  if ! offer_install "$missing"; then
    echo "Nothing was installed."
  fi
  PYTHON=$(find_python) || PYTHON=""
fi

if [ -z "$PYTHON" ]; then
  echo "Python 3 is still missing, so Shadow Reader cannot start. Install it, then run ./run.sh again."
  exit 1
fi

if ! command -v pdftotext >/dev/null 2>&1; then
  echo "Continuing without PDF import. Plain-text (.txt) files will still work."
  echo "Install Poppler later for PDF support, then restart ./run.sh."
fi

exec "$PYTHON" server.py
