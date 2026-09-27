from platform_parsers.ardupilot.dataflash_parser import (
    ArduPilotDataFlashParser,
)


PATH = "tests/fixtures/synthetic_ardupilot.bin"


print("=" * 70)
print("ARDUPILOT DATAFLASH PARSER TEST")
print("=" * 70)

print("\n[1] IDENTIFICATION")

result = ArduPilotDataFlashParser.identify(PATH)

print(result)

print("\n[2] PARSING")

parser = ArduPilotDataFlashParser(PATH)

evidence = parser.parse()

print("Platform:", evidence.metadata.platform)
print("Format:", evidence.metadata.format)

print("\n[3] RECORD COUNTS")

print("GPS records:      ", len(evidence.gps))
print("Commands:         ", len(evidence.commands))
print("Command ACKs:     ", len(evidence.command_acks))
print("States:           ", len(evidence.states))
print("Parameters:       ", len(evidence.parameters))
print("Events:           ", len(evidence.events))

print("\n[4] GPS RECORDS")

for gps in evidence.gps:
    print(gps)

print("\n[5] PARAMETERS")

for parameter in evidence.parameters:
    print(parameter)

print("\n[6] EVENTS")

for event in evidence.events:
    print(event)

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)
