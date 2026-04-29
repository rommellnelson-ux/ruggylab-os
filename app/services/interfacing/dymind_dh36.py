from typing import Any

import hl7


class DH36Parser:
    def __init__(self, raw_message: str):
        self.message_str = raw_message.strip()
        self.lines = [
            line for line in self.message_str.replace("\n", "\r").split("\r") if line
        ]
        try:
            self.h_message = hl7.parse(self.message_str)
        except Exception as exc:  # pragma: no cover - defensive parser boundary
            raise ValueError(f"Erreur de parsing HL7 brute: {exc}") from exc

    def _segment_fields(self, segment_name: str) -> list[str] | None:
        prefix = f"{segment_name}|"
        for line in self.lines:
            if line.startswith(prefix):
                return line.split("|")
        return None

    def _segments_fields(self, segment_name: str) -> list[list[str]]:
        prefix = f"{segment_name}|"
        return [line.split("|") for line in self.lines if line.startswith(prefix)]

    def get_info(self) -> dict[str, Any]:
        ipp = None
        barcode = None
        message_control_id = None
        equipment_serial = None

        msh_fields = self._segment_fields("MSH")
        if msh_fields:
            if len(msh_fields) > 2:
                equipment_serial = msh_fields[2] or None
            if len(msh_fields) > 9:
                message_control_id = msh_fields[9] or None

        pid_fields = self._segment_fields("PID")
        if pid_fields and len(pid_fields) > 3:
            ipp = pid_fields[3].split("^")[0] or None

        obr_fields = self._segment_fields("OBR")
        if obr_fields and len(obr_fields) > 3:
            barcode = obr_fields[3].split("^")[0] or None

        return {
            "ipp": ipp,
            "barcode": barcode,
            "message_control_id": message_control_id,
            "equipment_serial": equipment_serial,
        }

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

        for fields in self._segments_fields("OBX"):
            if len(fields) <= 5:
                continue
            raw_param_name = fields[3].split("^")[0]

            mapped_name = param_mapping.get(raw_param_name)
            if not mapped_name:
                continue

            try:
                results_map[mapped_name] = float(fields[5])
            except Exception:
                continue

        return results_map
