#   Copyright 2018 getcarrier.io
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import os
import re
from time import sleep

from dusty import constants as c
from dusty.utils import execute, find_ip, common_post_processing
from dusty.data_model.nikto.parser import NiktoXMLParser
from dusty.data_model.nmap.parser import NmapXMLParser
from dusty.data_model.zap.parser import ZapXmlParser
from dusty.data_model.sslyze.parser import SslyzeJSONParser
from dusty.data_model.masscan.parser import MasscanJSONParser
from dusty.data_model.w3af.parser import W3AFXMLParser


class DustyWrapper(object):
    @staticmethod
    def sslyze(config):
        exec_cmd = f'sslyze --regular --json_out=/tmp/sslyze.json --quiet {config["host"]}:{config["port"]}'
        execute(exec_cmd)
        result = SslyzeJSONParser("/tmp/sslyze.json", "SSlyze").items
        common_post_processing(config, result, "SSlyze")
        return result

    @staticmethod
    def masscan(config):
        host = config["host"]
        if not (find_ip(host)):
            host = find_ip(str(execute(f'getent hosts {host}')[0]))
            if len(host) > 0:
                host = host[0].strip()
        if host:
            excluded_addon = f'--exclude-ports {config.get("exclusions", None)}' if config.get("exclusions", None) else ""
            ports = config.get("inclusions", "0-65535")
            exec_cmd = f'masscan {host} -p {ports} -pU:{ports} --rate 1000 -oJ /tmp/masscan.json {excluded_addon}'
            execute(exec_cmd)
            result = MasscanJSONParser("/tmp/masscan.json", "masscan").items
            common_post_processing(config, result, "masscan")
            return result
        return []

    @staticmethod
    def nikto(config):
        if os.path.exists("/tmp/nikto.xml"):
            os.remove("/tmp/nikto.xml")
        exec_cmd = f'perl nikto.pl {config.get("param", "")} -h {config["host"]} -p {config["port"]} ' \
                   f'-Format xml -output /tmp/nikto.xml -Save /tmp/extended_nikto.xml'
        cwd = '/opt/nikto/program'
        execute(exec_cmd, cwd)
        result = NiktoXMLParser("/tmp/nikto.xml", "Nikto").items
        common_post_processing(config, result, "nikto")
        return result

    @staticmethod
    def nmap(config):
        excluded_addon = f'--exclude-ports {config.get("exclusions", None)}' if config.get("exclusions", None) else ""
        ports = config.get("inclusions", "0-65535")
        nse_scripts = config.get("nse_scripts", "ssl-date,http-mobileversion-checker,http-robots.txt,http-title,"
                                                "http-waf-detect,http-chrono,http-headers,http-comments-displayer,"
                                                "http-date")
        exec_cmd = f'nmap -PN -p{ports} {excluded_addon} ' \
                   f'--min-rate 1000 --max-retries 0 --max-rtt-timeout 200ms ' \
                   f'{config["host"]}'
        res = execute(exec_cmd)
        tcp_ports = ''
        udp_ports = ''
        for each in re.findall(r'([0-9]*/[tcp|udp])', str(res[0])):
            if '/t' in each:
                tcp_ports += f'{each.replace("/t", "")},'
            elif '/u' in each:
                udp_ports += f'{each.replace("/u", "")},'
        ports = f"-pT:{tcp_ports[:-1]}" if tcp_ports else ""
        ports += f" -pU:{udp_ports[:-1]}" if udp_ports else ""
        if not ports:
            return
        params = config.get("params", "-v -sVA")
        exec_cmd = f'nmap {params} {ports} ' \
                   f'--min-rate 1000 --max-retries 0 ' \
                   f'--script={nse_scripts} {config["host"]} -oX /tmp/nmap.xml'
        execute(exec_cmd)
        result = NmapXMLParser('/tmp/nmap.xml', "NMAP").items
        common_post_processing(config, result, "NMAP")
        return result


    @staticmethod
    def zap(config):
        if 'supervisor.sock no such file' in execute('supervisorctl restart zap')[0].decode('utf-8'):
            execute('/usr/bin/supervisord', communicate=False)
        sleep(20)
        if config.get('zap_context_file_path', None):
            context = os.path.join('/tmp', config.get('zap_context_file_path'))
            if os.path.exists(context):
                execute(f'zap-cli context import /tmp/{config.get("zap_context_file_path")}')
                execute(f'zap-cli quick-scan -s {config.get("scan_types", "xss,sqli")} {config.get("params", "")}'
                        f' -c "{context}" -l Informational'
                        f' {config.get("protocol")}://{config.get("host")}:{config.get("port")}')
        else:
            execute(f'zap-cli quick-scan -s {config.get("scan_types", "xss,sqli")} {config.get("params", "")}'
                    f'-l Informational {config.get("protocol")}://{config.get("host")}:{config.get("port")}')
        execute('zap-cli report -o /tmp/zap.xml -f xml')
        result = ZapXmlParser('/tmp/zap.xml', "ZAP").items
        execute('supervisorctl stop zap')
        common_post_processing(config, result, "ZAP")
        return result

    @staticmethod
    def w3af(config):
        config_file = config.get("config_file", "/tmp/w3af_full_audit.w3af")
        w3af_execution_command = f'w3af_console -y -n -s {config_file}'
        with open(config_file, 'r') as f:
            config_content = f.read()
        if '{target}' in config_content:
            config_content = config_content.format(
                target=f'{config.get("protocol")}://{config.get("host")}:{config.get("port")}',
                output_section=c.W3AF_OUTPUT_SECTION)
        with open(config_file, 'w') as f:
            f.write(config_content)
        execute(w3af_execution_command)
        result = W3AFXMLParser("/tmp/w3af.xml", "w3af").items
        common_post_processing(config, result, "w3af")
        return result

    @staticmethod
    def qualys(config):
        print(config)

    @staticmethod
    def burp(config):
        print(config)
