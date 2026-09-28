"""iRobot (Roomba/Braava) integration via `roombapy`, which talks to the
robot directly over local MQTT (no cloud account needed once you have its
local password). One-time setup per robot: put it in pairing mode (hold the
CLEAN button until it beeps blue), then run
`python -m roombapy.getpassword <robot-ip>` to get its BLID + local
password. Set IROBOT_ROBOT_IPS="ip:blid:password,ip2:blid2:password2" in
.env (comma-separated per robot).

Reading status never needs confirmation; starting/stopping/docking a
cleaning run always does - it's a physical robot moving around the house.
"""
from __future__ import annotations

from typing import Any

from src.core.settings import get_settings
from src.core.tool_registry import PendingConfirmation, Tool, register


def _robots() -> list[dict[str, str]]:
    robots = []
    for entry in get_settings().irobot_robot_entries:
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        robots.append({"ip": parts[0], "blid": parts[1], "password": parts[2]})
    return robots


def _is_configured() -> bool:
    return bool(_robots())


def _find_robot(ip: str) -> dict[str, str] | None:
    return next((r for r in _robots() if r["ip"] == ip), None)


def _connect(ip: str, blid: str, password: str):
    from roombapy import Roomba

    robot = Roomba(remote_ip=ip, blid=blid, password=password)
    robot.connect()
    return robot


def list_irobot_robots() -> dict[str, Any]:
    if not _is_configured():
        return {"error": "iRobot isn't configured yet. Set IROBOT_ROBOT_IPS (ip:blid:password,...) in .env."}
    results = []
    for r in _robots():
        try:
            robot = _connect(r["ip"], r["blid"], r["password"])
            reported = (robot.master_state or {}).get("state", {}).get("reported", {})
            results.append({
                "ip": r["ip"],
                "name": reported.get("name"),
                "battery_pct": reported.get("batPct"),
                "phase": (reported.get("cleanMissionStatus") or {}).get("phase"),
            })
            robot.disconnect()
        except Exception as exc:  # noqa: BLE001
            results.append({"ip": r["ip"], "error": str(exc)})
    return {"robots": results}


def _command(ip: str, command: str) -> dict[str, Any]:
    robot_cfg = _find_robot(ip)
    if robot_cfg is None:
        return {"error": f"No robot configured with ip {ip}"}
    robot = _connect(robot_cfg["ip"], robot_cfg["blid"], robot_cfg["password"])
    try:
        robot.send_command(command)
    finally:
        robot.disconnect()
    return {"status": "sent", "command": command}


def request_irobot_command(ip: str, robot_label: str, command: str) -> Any:
    if not _is_configured():
        return {"error": "iRobot isn't configured yet. Set IROBOT_ROBOT_IPS in .env."}
    if command not in ("start", "stop", "pause", "dock"):
        return {"error": "command must be one of: start, stop, pause, dock"}
    return PendingConfirmation(
        action_type="irobot_command",
        summary=f"Send '{command}' to '{robot_label}'?",
        payload={"ip": ip, "command": command},
    )


register(Tool(
    name="list_irobot_robots",
    description="List iRobot Roomba/Braava robots and their status (battery percentage, cleaning phase).",
    parameters={"type": "object", "properties": {}},
    handler=list_irobot_robots,
))

register(Tool(
    name="request_irobot_command",
    description="Request starting/stopping/pausing/docking an iRobot cleaning run. Always requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "ip": {"type": "string"},
            "robot_label": {"type": "string"},
            "command": {"type": "string", "enum": ["start", "stop", "pause", "dock"]},
        },
        "required": ["ip", "robot_label", "command"],
    },
    handler=request_irobot_command,
    requires_confirmation=True,
    executor=lambda payload: _command(payload["ip"], payload["command"]),
))
