#!/usr/bin/env python3

import bcrypt
import time
import random
import sys

start = time.time()
if len(sys.argv) == 2:
    passwd = sys.argv[1]
else:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    passwd = ''.join(random.choices(alphabet, k=30))
    
salt = bcrypt.gensalt(rounds=10)
hashed = bcrypt.hashpw(bytes(passwd.encode("utf-8")), salt).decode('utf-8')

end = time.time()
print("Time             : %f s" % (end - start))
print("Hashed API Token : %s" % hashed)
print("API Token        : %s" % passwd)
