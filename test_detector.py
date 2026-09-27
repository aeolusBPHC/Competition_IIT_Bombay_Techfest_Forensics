from platform_parsers.common.platform_detector import PlatformDetector
from platform_parsers.common.registry import get_parser_classes

path = (
    "repository/cases/"
    "CASE-001/"
    "EVD-20260919-175126/"
    "evidence/"
    "17_02_27.ulg"
)

detector = PlatformDetector()

for parser_class in get_parser_classes():
    detector.register(parser_class)

print("=" * 60)
print("FORENSIC PLATFORM DETECTION TEST")
print("=" * 60)

results = detector.detect(path)

print("\nAll detections:")

for result in results:
    print(result)

print("\nBest match:")

best = detector.best_match(path)

print(best)

print("\n" + "=" * 60)
