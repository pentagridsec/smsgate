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
import configparser
import logging
from dataclasses import dataclass
from typing import List

import helper


@dataclass
class ModemConfig:
    identifier: str
    enabled: bool
    baud: int
    port: str
    pin: str
    wait_for_start: int
    wait_for_delivery: bool
    phone_number: str
    ussd_account_balance: str
    ussd_account_balance_regexp: str
    ussd_currency: str
    account_balance_warning: float
    account_balance_critical: float
    prefixes: List[str]
    costs_per_sms: float
    health_check_interval: int
    sms_self_test_interval: str
    imei: str
    encoding: str
    email_address: str

    def verify(self) -> bool:

        if not self.enabled:
            return True  # There is nothing to check

        assert self.identifier is not None

        l = logging.getLogger(f"ModemConfig [{self.identifier}]")
        if self.account_balance_critical > self.account_balance_warning:
            l.error(
                "Account balance threshold for critical larger than warning threshold."
            )
            return False

        for prefix in self.prefixes:
            if not helper.cleanup_phone_number(prefix):
                l.error(f"Prefix {prefix} is not valid.")
                return False

        if self.health_check_interval <= 60:
            l.warning("It is not recommended to perform health checks too often.")
            # no return

        if not helper.cleanup_phone_number(self.phone_number):
            l.error(f"Phone number {self.phone_number} is not valid.")
            return False

        if self.ussd_account_balance is None or self.ussd_account_balance == "":
            l.warning("No USSD definition for checking account balance defined.")
            # no return

        if self.ussd_account_balance and (
                self.ussd_account_balance_regexp is None
                or self.ussd_account_balance_regexp == ""
        ):
            l.warning(
                "There is no regular expression defined to extract the account balance from the USSD response."
            )
            # no return

        if self.sms_self_test_interval not in ["monthly", "weekly", "daily"]:
            l.warning("The SMS self test interval cannot be parsed.")
            return False

        if "*" in self.port and (self.imei is None or self.imei == ""):
            l.warning(
                "There is no fixed serial port set and the expected IMEI is not specified, too."
            )
            return False

        return True


def read_modem_config(identifier: str, sim_config: configparser.ConfigParser,
                      sms_self_test_interval: str) -> ModemConfig:
    return ModemConfig(
        identifier,
        sim_config.getboolean(identifier, "enabled", fallback=True),
        sim_config.getint(identifier, "baud", fallback=115200),
        sim_config.get(identifier, "port"),
        sim_config.get(identifier, "pin", fallback=None),
        sim_config.getint(identifier, "wait_for_start", fallback=60),
        sim_config.getboolean(identifier, "wait_for_delivery", fallback=False),
        sim_config.get(identifier, "phone_number", fallback=None),
        sim_config.get(identifier, "ussd_account_balance", fallback=None),
        sim_config.get(identifier, "ussd_account_balance_regexp", fallback=None),
        sim_config.get(identifier, "currency", fallback="EUR"),
        sim_config.getfloat(identifier, "account_balance_warning", fallback=5),
        sim_config.getfloat(identifier, "account_balance_critical", fallback=1),
        sim_config.get(identifier, "prefixes", fallback="").split(),
        sim_config.getfloat(identifier, "costs_per_sms"),
        sim_config.getint(identifier, "health_check_interval", fallback=600),
        sms_self_test_interval,
        sim_config.get(identifier, "imei", fallback=None),
        sim_config.get(identifier, "encoding", fallback="GSM"),
        sim_config.get(identifier, "email_address", fallback=None)
    )
