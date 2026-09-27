from pathlib import Path

from platform_parsers.common.platform_detector import PlatformDetector
from platform_parsers.ardupilot.dataflash_parser import ArduPilotDataFlashParser


def main():
    fixture = Path("tests/fixtures/synthetic_ardupilot_forensics.bin")

    print("=" * 60)
    print("ARDUPILOT FORENSICS DETECTION TEST")
    print("=" * 60)

    print(f"\nTesting: {fixture}")

    detector = PlatformDetector()
    detector.register(ArduPilotDataFlashParser)

    results = detector.detect(fixture)

    print("\nAll detections:")
    for result in results:
        print(result)

    best = detector.best_match(fixture)

    print("\nBest match:")
    print(best)

    if best is None:
        raise RuntimeError("No parser detected the synthetic ArduPilot fixture")

    if best["platform"] != "ArduPilot":
        raise RuntimeError("Incorrect platform detected")

    if best["format"] != "DataFlash":
        raise RuntimeError("Incorrect format detected")

    print("\nDetection test: PASSED")


if __name__ == "__main__":
    main()
