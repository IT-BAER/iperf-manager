import unittest

from core.config_model import ClientConfig, TestConfig


def _url_errors(server_agent):
    cfg = TestConfig(server_agent=server_agent,
                     clients=[ClientConfig(name='c1', agent='https://10.0.0.2:9001', target='10.0.0.1')])
    return [e for e in cfg.validate() if 'URL' in e]


class ServerUrlValidationTest(unittest.TestCase):
    def test_accepts_http_and_https(self):
        self.assertEqual(_url_errors('http://10.0.0.1:9001'), [])
        self.assertEqual(_url_errors('https://10.0.0.1:9001'), [])

    def test_rejects_other_schemes(self):
        self.assertEqual(len(_url_errors('ftp://10.0.0.1:9001')), 1)


if __name__ == '__main__':
    unittest.main()
