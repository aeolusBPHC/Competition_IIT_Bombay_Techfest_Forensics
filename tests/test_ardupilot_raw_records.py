from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)

PATH = "tests/fixtures/synthetic_ardupilot.bin"

parser = ArduPilotDataFlashParser(PATH)

print("=" * 70)
print("RAW ARDUPILOT DATAFLASH RECORD TEST")
print("=" * 70)

count = 0

for record in parser._iter_records():

    count += 1

    print("\nRecord", count)
    print("Message:", record["name"])
    print("Message ID:", record["message_type"])
    print("Format:", record["format"])
    print("Labels:", record["labels"])
    print("Values:", record["values"])

print("\nTotal records:", count)

print("=" * 70)
