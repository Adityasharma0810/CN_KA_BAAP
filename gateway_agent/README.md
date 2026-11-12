"""Experience Budget Gateway Agent - README.

The gateway agent is a standalone, lightweight service that runs on the
computer or router managing household traffic. It is independent of the full
development repository.

Install (Linux):
    pip install experience-budget-agent   # or pip install -e . from this dir
    EB_GATEWAY_ID=gw-home-01 \
    EB_CONTROL_PLANE_URL=https://experience-budget.example.com \
    EB_AGENT_TOKEN=<token> \
    EB_WAN_INTERFACE=wlan0 \
    EB_LAN_INTERFACE=ap0 \
    python -m gateway_agent

Run as a systemd service:
    sudo cp installers/experience-budget-agent.service /etc/systemd/system/
    sudo systemctl enable --now experience-budget-agent

The agent initiates an outbound authenticated WebSocket to the control plane.
It never exposes an inbound management port to the internet.

Capabilities are detected honestly; unsupported features run in observation-only
mode and are reported as such to the cloud dashboard.
"""
