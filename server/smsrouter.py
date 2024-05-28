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
from typing import Optional, List

from modem import Modem

class SmsRouter:
    """Simple router that decides via which modem an SMS should be sent.
    First, the algorithm checks for valid phone number prefixes. Each modem/SIM
    can be registered for a prefix. Second, it checks for costs. Furthermore, the
    router checks if the modem is available.

    There is no sophisticated modeling of prices. Currencies do not exist in this model.
    Foreign SIMs might be managed in a foreign currency and to handle
    this, you could separate the world into corresponding prefixes.

    """

    def __init__(self) -> None:
        """
        Create a new SmsRouter object.
        """
        self.routes = {}
        self.costs = {}
        self.modem = {}

    def add(self, identifier: str, prefixes: List[str], costs: float, modem: Modem) -> None:
        """
        Add routes to the table.
        @param identifier: A modem identifier that this route belongs to.
        @param prefixes: A list of phone number prefixes such as "+49152" and "+49".
        @param costs: Costs per SMS, but without a currency.
        @param modem: A modem object to allow checking if the modem is ready.
        """

        self.modem[identifier] = modem
        
        # costs for sending SMS in a table like:
        # '01' -> 0.05
        self.costs[identifier] = costs

        # add routes in a table like:
        # +49152 -> [ '01', '03' ]
        # +49    -> [ '01', '04' ]
        # which assignes prefixes to modem identifier
        for prefix in prefixes:
            if prefix not in self.routes:
                self.routes[prefix] = {identifier}
            else:
                self.routes[prefix].add(identifier)



    def get(self, prefix: str) -> Optional[str]:
        """
        Get a route for a phone number prefix.
        @return: Returns a modem identifier via which a SMS should be sent. If there was no suitable modem,
            None is returned.
        """

        candidates = set()

        # First, create a set of canidates
        for i in range(0, len(prefix) - 1):
            sub_prefix = prefix[0: len(prefix) - i]
            if sub_prefix in self.routes:
                for c in self.routes[sub_prefix]:

                    # c is a modem identifier
                    # Check if the modem is ready, then add itr
                    state, log = self.modems[c].get_health_state()
                    if state == "OK":
                        candidates.add(c)

        # Second, return the one with the lowest cost
        if len(candidates) > 0:
            return min(candidates, key=lambda k: self.costs[k])
        else:
            return None
