from pathlib import Path

from platform_parsers.common.platform_detector import PlatformDetector
from platform_parsers.common.registry import get_parser_classes


def create_test_file(filename):
    path = Path("/tmp") / filename
    path.write_bytes(b"TEST EVIDENCE")
    return path


detector = PlatformDetector()

for parser_class in get_parser_classes():
    detector.register(parser_class)


test_files = [
    "test.ulg",
    "test.bin",
    "test.log",
    "test.tlog",
    "test.txt",
]


print("=" * 70)
print("MULTI-PLATFORM DETECTION TEST")
print("=" * 70)


for filename in test_files:

    path = create_test_file(filename)

    print()
    print("-" * 70)
    print("Testing:", path)

    results = detector.detect(path)

    if not results:
        print("No parser detected this file.")
    else:
        for result in results:
            print(result)


print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
