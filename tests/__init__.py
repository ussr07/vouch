"""Offline tests: never reach the network."""
import os

# The growth step looks up market data and news; the tests check it with fakes instead.
os.environ["VOUCH_GROWTH"] = "0"
