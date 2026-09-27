from pathlib import Path


class PlatformDetector:
    """
    Detect the likely platform and evidence format for a
    drone forensic artifact.

    Detection is deliberately conservative.

    The detector reports observations and confidence rather
    than pretending that platform identification is certain.
    """

    def __init__(self):
        self.detectors = []

    def register(self, parser_class):
        """
        Register a platform parser that implements identify().
        """

        self.detectors.append(parser_class)

    def detect(self, evidence_path):
        """
        Run all registered platform detectors.

        Returns a list of detection results.
        """

        path = Path(evidence_path)

        results = []

        for parser_class in self.detectors:

            try:
                result = parser_class.identify(path)

                if result.get("supported"):
                    results.append(result)

            except Exception as exc:
                results.append(
                    {
                        "supported": False,
                        "platform": getattr(
                            parser_class,
                            "platform_name",
                            "UNKNOWN",
                        ),
                        "format": None,
                        "confidence": "ERROR",
                        "reason": str(exc),
                    }
                )

        return results

    def best_match(self, evidence_path):
        """
        Return the highest-confidence detection result.

        If no parser recognizes the evidence, return None.
        """

        results = self.detect(evidence_path)

        if not results:
            return None

        confidence_order = {
            "HIGH": 3,
            "MEDIUM": 2,
            "LOW": 1,
            "NONE": 0,
            "ERROR": -1,
        }

        return max(
            results,
            key=lambda result: confidence_order.get(
                result.get("confidence", "NONE"),
                0,
            ),
        )
