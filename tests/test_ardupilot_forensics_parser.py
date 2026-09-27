from pathlib import Path

from platform_parsers.ardupilot.dataflash_parser import ArduPilotDataFlashParser


def main():
    fixture = Path("tests/fixtures/synthetic_ardupilot_forensics.bin")

    print("=" * 60)
    print("ARDUPILOT FORENSICS NORMALIZED PARSER TEST")
    print("=" * 60)

    parser = ArduPilotDataFlashParser(fixture)

    print("\n[1] IDENTIFICATION")
    identification = parser.identify(fixture)
    print(identification)

    if not identification.get("supported"):
        raise RuntimeError("Synthetic fixture was not detected")

    print("\n[2] PARSING")
    evidence = parser.parse()

    print(f"Platform: {evidence.metadata.platform}")
    print(f"Format:   {evidence.metadata.format}")

    print("\n[3] RECORD COUNTS")
    print(f"GPS records:      {len(evidence.gps)}")
    print(f"Commands:         {len(evidence.commands)}")
    print(f"Command ACKs:     {len(evidence.command_acks)}")
    print(f"States:           {len(evidence.states)}")
    print(f"Parameters:       {len(evidence.parameters)}")
    print(f"Events:           {len(evidence.events)}")

    print("\n[4] GPS")
    for record in evidence.gps[:3]:
        print(record)

    print("\n[5] COMMANDS")
    for record in evidence.commands[:3]:
        print(record)

    print("\n[6] STATES")
    for record in evidence.states[:5]:
        print(record)

    print("\n[7] PARAMETERS")
    for record in evidence.parameters[:5]:
        print(record)

    print("\n[8] EVENTS")
    for record in evidence.events[:10]:
        print(record)

    print("\nParser test completed.")


if __name__ == "__main__":
    main()
