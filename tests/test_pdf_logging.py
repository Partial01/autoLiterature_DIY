import unittest
from unittest.mock import Mock, patch

import requests

from autoliterature.pdfs import pdfDownload


class PdfLoggingTests(unittest.TestCase):
    def test_failure_logs_omit_credentials_query_and_fragment(self):
        url = ('https://test-user:test-password@example.org/paper.pdf'
               '?token=test-token&signature=test-signature#test-fragment')
        for error in (None, requests.ConnectionError(url)):
            with self.subTest(error=type(error).__name__):
                client = pdfDownload()
                with patch.object(client.sess, 'get', side_effect=error,
                                  return_value=Mock(headers={'Content-Type': 'text/html'})) as get:
                    with self.assertLogs('PDFs', level='INFO') as logs:
                        self.assertIsNone(client.fetch(url))
                get.assert_called_once_with(url, auth=None)
                output = ' '.join(logs.output)
                self.assertIn('https://example.org/paper.pdf', output)
                for secret in ('test-user', 'test-password', 'test-token',
                               'test-signature', 'test-fragment'):
                    self.assertNotIn(secret, output)

    def test_success_retains_original_download_url_and_authentication(self):
        client = pdfDownload()
        url = 'https://example.org/paper.pdf?signature=test-signature'
        auth = ('test-user', 'test-password')
        response = Mock(headers={'Content-Type': 'application/pdf'}, content=b'%PDF-1.7')
        with patch.object(client.sess, 'get', return_value=response) as get:
            result = client.fetch(url, auth=auth)
        get.assert_called_once_with(url, auth=auth)
        self.assertEqual(result, {'pdf': b'%PDF-1.7', 'url': url})

    def test_invalid_url_is_not_echoed_in_error_log(self):
        for url in ('https://test-user:test-password@[invalid?token=test-token',
                    'test-user:test-password@example.org/paper.pdf',
                    'https:///test-password?token=test-token'):
            with self.subTest(url=url):
                client = pdfDownload()
                with patch.object(client.sess, 'get', side_effect=requests.exceptions.InvalidURL(url)):
                    with self.assertLogs('PDFs', level='ERROR') as logs:
                        self.assertIsNone(client.fetch(url))
                self.assertIn('<invalid URL>', logs.output[0])
                self.assertNotIn('test-', logs.output[0])


if __name__ == '__main__':
    unittest.main()
