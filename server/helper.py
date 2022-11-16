# -----------------------------------------------------------------------------
# Copyright (c) 2022 Martin Schobert, Pentagrid AG
#
# All rights reserved.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
#  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
#  ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#  WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#  DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
#  ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#  (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#  LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#  ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#  (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#  The views and conclusions contained in the software and documentation are those
#  of the authors and should not be interpreted as representing official policies,
#  either expressed or implied, of the project.
#
#  NON-MILITARY-USAGE CLAUSE
#  Redistribution and use in source and binary form for military use and
#  military research is not permitted. Infringement of these clauses may
#  result in publishing the source code of the utilizing applications and
#  libraries to the public. As this software is developed, tested and
#  reviewed by *international* volunteers, this clause shall not be refused
#  due to the matter of *national* security concerns.
# -----------------------------------------------------------------------------

import logging
import os
import re
import stat
import sys
from typing import Optional, List

import bcrypt


def cleanup_phone_number(phone_number: str) -> Optional[str]:
    """
    This function cleans-up phone numbers and removes seperator characters and implements a very basic
    phone number check.

    If there is the need to do further checks, this library could help:
    https://github.com/daviddrysdale/python-phonenumbers

    @param phone_number: It expects phone numbers to be in the ^\+\d+$ format. It removes any
    non-digit (+ is allowed).
    @return: The function returns either a uniform
    phone number in the before-mentioned format or returns None.
    """

    phone_number = re.sub("[^\+\d]", "", phone_number)
    if re.match("^\+\d+$", phone_number):
        return phone_number
    else:
        return None


def check_file_permissions(filename: str) -> bool:
    """
    Check if a file is readable by other users, which indicates misconfiguration.
    @param filename: The name of the file as string.
    @return: If file is not readable by others, True is returned. Otherwise the program stop with an error message.
    """
    st = os.stat(filename)
    if st.st_mode & stat.S_IROTH:
        logging.critical(
            f"Configuration file {filename} is readable by others. Stopping here."
        )
        sys.exit(1)
    else:
        return True


def get_highest_warning_level(state_list: List[Optional[str]]) -> str:
    """
    For a list of strings indicating severity levels, return the highest value.
    @param state_list: A list of strings, such as "OK", "WARNING", "CRITICAL".
    @return: Returns the highest level.
    """
    highest = "OK"

    for i in state_list:
        if i == "CRITICAL":
            return "CRITICAL"
        elif i == "WARNING" and highest == "OK":
            highest = "WARNING"

    return highest


def hexdump(src: bytes, length: int = 16) -> str:
    """
    Convert an input into a hexdump string.
    @param src: The input to print
    @param length: Number of bytes to show per line.
    @return: A string containing the hex dump.
    """
    FILTER = "".join([(len(repr(chr(x))) == 3) and chr(x) or "." for x in range(256)])
    lines = []
    for c in range(0, len(src), length):
        chars = src[c: c + length]
        hexstr = " ".join(["%02x" % ord(x) for x in chars])
        printable = "".join(
            ["%s" % ((ord(x) <= 127 and FILTER[ord(x)]) or ".") for x in chars]
        )
        lines.append("%04x  %-*s  %s\n" % (c, length * 3, hexstr, printable))
    return "".join(lines)


def check_password(password_clear: str, password_hashed: str) -> bool:
    """
    Compare a clear-text password to a password hash by converting the clear-text password via bcrypt first.
    @param password_clear: The clear-text password as input.
    @param password_hashed: The stored password hash.
    @return: Returns either True or False.
    """
    a = password_clear.encode("utf-8")
    b = password_hashed.encode("utf-8")
    return bcrypt.checkpw(bytes(a), bytes(b))


def check_token_in_list(token: str, token_list: List[str]) -> bool:
    """
    Check if a clear-text password or token is in a list of bcrypt hashes.
    @param token: The clear-text password or token.
    @param token_list: A list of bcrypt hashes for passwords/tokens.
    @return: Returns True if a token/password was found.
    """
    for t in token_list:
        if check_password(token, t):
            return True
    return False
