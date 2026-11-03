#!/usr/bin/env python3
"""Lane 08 strict GPU qualification receipt gate; no hardware or network access.

A receipt indexes *reviewed evidence*, not a cryptographic evidence verifier.
Missing, malformed or non-true checks deny promotion. Use --receipt FILE.
"""
import argparse
import json
import pathlib
import sys
import unittest

CHECKS = ("identity", "ioctl", "shader", "frames", "pixels", "stability", "rollback", "audit")


def evaluate(receipt):
    if not isinstance(receipt, dict):
        return False, list(CHECKS)
    missing = [key for key in CHECKS if receipt.get(key) is not True]
    return not missing, missing


class GateTests(unittest.TestCase):
    def test_missing_receipt_fails(self):
        self.assertEqual(evaluate({}), (False, list(CHECKS)))

    def test_incomplete_receipt_fails(self):
        valid = dict.fromkeys(CHECKS, True)
        for key in CHECKS:
            incomplete = valid.copy()
            incomplete[key] = False
            self.assertEqual(evaluate(incomplete), (False, [key]))

    def test_truthy_strings_and_numbers_not_accepted(self):
        for value in ("true", 1, [], {}, None):
            incomplete = dict.fromkeys(CHECKS, True)
            incomplete["pixels"] = value
            self.assertEqual(evaluate(incomplete), (False, ["pixels"]))

    def test_complete_receipt_passes(self):
        self.assertEqual(evaluate(dict.fromkeys(CHECKS, True)), (True, []))

    def test_non_object_fails(self):
        self.assertFalse(evaluate([True] * 8)[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=pathlib.Path, help="Reviewed evidence-index JSON")
    args = parser.parse_args()
    if args.receipt is None:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(GateTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    try:
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"NOT QUALIFIED: receipt unavailable or invalid: {exc}", file=sys.stderr)
        return 2
    passed, missing = evaluate(receipt)
    print("GATE PASS (receipt index only; independent evidence review still required)"
          if passed else f"NOT QUALIFIED: missing/false {', '.join(missing)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
