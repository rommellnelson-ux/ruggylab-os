from typing import Any

import hl7


class DH36Parser:
    def __init__(self, raw_message: str):
        self.message_str = raw_message.strip()
        try:
            self.h_message = hl7.parse(self.message_str)
        except Exception as exc:  # pragma: no cover - defensive parser boundary
            raise ValueError(f"Erreur de parsing HL7 brute: {exc}") from exc

    def get_info(self) -> dict[str, Any]:
        ipp = None
        barcode = None

        try:
            pid_segment = self.h_message.segment("PID")
            ipp = str(pid_segment[3][0][0])
        except Exception:
            ipp = None

        try:
            obr_segment = self.h_message.segment("OBR")
            barcode = str(obr_segment[3][0][0])
        except Exception:
            barcode = None

        return {"ipp": ipp, "barcode": barcode}

    def parse_results(self) -> dict[str, float]:
        param_mapping = {
            "WBC": "WBC",
            "RBC": "RBC",
            "HGB": "HGB",
            "HCT": "HCT",
            "MCV": "MCV",
            "MCH": "MCH",
            "MCHC": "MCHC",
            "PLT": "PLT",
        }
        results_map: dict[str, float] = {}

        for segment in self.h_message.segments("OBX"):
            try:
                raw_param_name = str(segment[3][0][0])
            except Exception:
                raw_param_name = str(segment[3])

            mapped_name = param_mapping.get(raw_param_name)
            if not mapped_name:
                continue

            try:
                results_map[mapped_name] = float(str(segment[5]))
            except Exception:
                continue

        return results_map
