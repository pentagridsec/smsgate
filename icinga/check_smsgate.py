#!/usr/bin/env python3
#
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


import argparse
import xmlrpc.client, http.client
import ssl
import os
import sys

def run_test(host: str, port: int, cafile: str, api_token: str) -> None:
    context = ssl.create_default_context()
    context.load_verify_locations(cafile)

    try:
        s = xmlrpc.client.ServerProxy("https://%s:%d" % (host, port), context=context)

        result = s.get_health_state(api_token)        
        print(result[0] + " " + result[1])
        
        if result[0] == "OK":
            sys.exit(0)
        elif result[0] == "WARNING":
            sys.exit(1)
        elif result[0] == "CRITICAL":
            sys.exit(2)
        else:
            sys.exit(3)
            
    except ConnectionRefusedError:
        print(f"CRITICAL Connection to {host}:{port} refused.")
        sys.exit(2)


def main() -> None:
    """
    Entry point
    """
    parser = argparse.ArgumentParser(description='Check SMSGate health status.')
    parser.add_argument('--host', metavar='HOSTNAME', help='Hostname of the server API.', default="localhost")
    parser.add_argument('--port', metavar='PORT', type=int, help='Port number of the server API.', default=7000)
    parser.add_argument('--ca', metavar='CAFILE', help='The CA certificate file.')
    parser.add_argument('--api-token', metavar='TOKEN', help='The API token to use (prefer ENV variable SMSGATE_APITOKEN).')

    args = parser.parse_args()

    run_test(args.host, args.port, args.ca if "ca" in args else None, os.getenv("SMSGATE_APITOKEN", args.api_token))
    
if __name__ == "__main__":
    main()
    
