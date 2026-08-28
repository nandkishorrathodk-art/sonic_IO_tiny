"""
Unit tests for Security Tool Parsers (Nuclei, Nmap, ffuf).
"""

import pytest
from sonic.tools.ffuf import FfufParser
from sonic.tools.nmap import NmapParser
from sonic.tools.nuclei import NucleiParser


def test_nuclei_parser_ndjson():
    raw_nuclei = """
{"template-id":"cve-2021-44228","info":{"name":"Apache Log4j RCE","severity":"critical","tags":["rce","cve","cve2021"],"classification":{"cvss-score":10.0,"cve-id":["CVE-2021-44228"]}},"matcher-name":"log4j-rce","matched-at":"http://target.com:8080","curl-command":"curl -H 'X-Api-Version: ${jndi:ldap://...}' http://target.com:8080","request":"GET / HTTP/1.1\\nHost: target.com\\n","response":"HTTP/1.1 200 OK\\n"}
{"template-id":"cors-wildcard","info":{"name":"CORS Origin Misconfiguration","severity":"medium","tags":["cors"]},"matched-at":"http://target.com/api","curl-command":"curl -H 'Origin: https://evil.com' http://target.com/api"}
"""
    results = NucleiParser.parse_json_stream(raw_nuclei)
    assert len(results) == 2

    # Verify first finding
    f1 = results[0]
    assert f1.template_id == "cve-2021-44228"
    assert f1.severity == "critical"
    assert f1.cve_id == "CVE-2021-44228"
    assert f1.cvss_score == 10.0
    assert "Cross-Site" not in f1.vulnerability_class
    assert "Remote Code Execution" in f1.vulnerability_class
    assert "curl" in f1.curl_command

    # Verify second finding
    f2 = results[1]
    assert f2.severity == "medium"
    assert f2.vulnerability_class == "CORS Misconfiguration"


def test_nmap_parser_text():
    raw_nmap = """
Starting Nmap 7.94 ( https://nmap.org )
Nmap scan report for api.example.com (192.168.1.50)
Host is up (0.0020s latency).

PORT     STATE SERVICE VERSION
22/tcp   open  ssh     OpenSSH 8.9p1 Ubuntu
80/tcp   open  http    nginx 1.18.0
443/tcp  open  https   nginx 1.18.0
3306/tcp open  mysql   MySQL 8.0.32
"""
    hosts = NmapParser.parse_text(raw_nmap)
    assert len(hosts) == 1
    h = hosts[0]
    assert h.ip == "192.168.1.50"
    assert len(h.ports) == 4

    open_ports = [p.port_id for p in h.ports]
    assert open_ports == [22, 80, 443, 3306]
    assert h.ports[0].service_name == "ssh"
    assert "OpenSSH" in h.ports[0].product


def test_ffuf_parser():
    raw_ffuf = """
{
  "results": [
    {
      "input": {"FUZZ": "admin"},
      "url": "http://example.com/admin",
      "status": 200,
      "length": 1420,
      "words": 150,
      "lines": 35,
      "content-type": "text/html",
      "redirectlocation": ""
    },
    {
      "input": {"FUZZ": "api/v1"},
      "url": "http://example.com/api/v1",
      "status": 403,
      "length": 250,
      "words": 20,
      "lines": 5,
      "content-type": "application/json",
      "redirectlocation": ""
    }
  ]
}
"""
    matches = FfufParser.parse_json(raw_ffuf)
    assert len(matches) == 2
    assert matches[0].input_keyword == "admin"
    assert matches[0].status_code == 200
    assert matches[1].status_code == 403
