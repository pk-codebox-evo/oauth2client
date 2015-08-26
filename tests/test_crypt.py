# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys
import unittest

import mock

from oauth2client import _helpers
from oauth2client.client import HAS_OPENSSL
from oauth2client.client import SignedJwtAssertionCredentials
from oauth2client import crypt


def datafile(filename):
    f = open(os.path.join(os.path.dirname(__file__), 'data', filename), 'rb')
    data = f.read()
    f.close()
    return data


class Test__bad_pkcs12_key_as_pem(unittest.TestCase):

    def test_fails(self):
        self.assertRaises(NotImplementedError, crypt._bad_pkcs12_key_as_pem)


class Test_pkcs12_key_as_pem(unittest.TestCase):

    def _make_signed_jwt_creds(self, private_key_file='privatekey.p12',
                               private_key=None):
        private_key = private_key or datafile(private_key_file)
        return SignedJwtAssertionCredentials(
            'some_account@example.com',
            private_key,
            scope='read+write',
            sub='joe@example.org')

    def _succeeds_helper(self, password=None):
        self.assertEqual(True, HAS_OPENSSL)

        credentials = self._make_signed_jwt_creds()
        if password is None:
            password = credentials.private_key_password
        pem_contents = crypt.pkcs12_key_as_pem(credentials.private_key,
                                               password)
        pkcs12_key_as_pem = datafile('pem_from_pkcs12.pem')
        pkcs12_key_as_pem = _helpers._parse_pem_key(pkcs12_key_as_pem)
        alternate_pem = datafile('pem_from_pkcs12_alternate.pem')
        self.assertTrue(pem_contents in [pkcs12_key_as_pem, alternate_pem])

    def test_succeeds(self):
        self._succeeds_helper()

    def test_succeeds_with_unicode_password(self):
        password = u'notasecret'
        self._succeeds_helper(password)

    def test_with_nonsense_key(self):
        from OpenSSL import crypto
        credentials = self._make_signed_jwt_creds(private_key=b'NOT_A_KEY')
        self.assertRaises(crypto.Error, crypt.pkcs12_key_as_pem,
                          credentials.private_key,
                          credentials.private_key_password)


class Test__verify_signature(unittest.TestCase):

    def test_success_single_cert(self):
        cert_value = 'cert-value'
        certs = {None: cert_value}
        message = object()
        signature = object()

        verifier = mock.MagicMock()
        verifier.verify = mock.MagicMock(name='verify', return_value=True)
        with mock.patch('oauth2client.crypt.Verifier') as Verifier:
            Verifier.from_string = mock.MagicMock(name='from_string',
                                                  return_value=verifier)
            result = crypt._verify_signature(message, signature, certs)
            self.assertEqual(result, None)

            # Make sure our mocks were called as expected.
            Verifier.from_string.assert_called_once_with(cert_value,
                                                         is_x509_cert=True)
            verifier.verify.assert_called_once_with(message, signature)

    def test_success_multiple_certs(self):
        cert_value1 = 'cert-value1'
        cert_value2 = 'cert-value2'
        cert_value3 = 'cert-value3'
        certs = _MockOrderedDict(cert_value1, cert_value2, cert_value3)
        message = object()
        signature = object()

        verifier = mock.MagicMock()
        # Use side_effect to force all 3 cert values to be used by failing
        # to verify on the first two.
        verifier.verify = mock.MagicMock(name='verify',
                                         side_effect=[False, False, True])
        with mock.patch('oauth2client.crypt.Verifier') as Verifier:
            Verifier.from_string = mock.MagicMock(name='from_string',
                                                  return_value=verifier)
            result = crypt._verify_signature(message, signature, certs)
            self.assertEqual(result, None)

            # Make sure our mocks were called three times.
            expected_from_string_calls = [
                mock.call(cert_value1, is_x509_cert=True),
                mock.call(cert_value2, is_x509_cert=True),
                mock.call(cert_value3, is_x509_cert=True),
            ]
            self.assertEqual(Verifier.from_string.mock_calls,
                             expected_from_string_calls)
            expected_verify_calls = [mock.call(message, signature)] * 3
            self.assertEqual(verifier.verify.mock_calls,
                             expected_verify_calls)

    def test_failure(self):
        cert_value = 'cert-value'
        certs = {None: cert_value}
        message = object()
        signature = object()

        verifier = mock.MagicMock()
        verifier.verify = mock.MagicMock(name='verify', return_value=False)
        with mock.patch('oauth2client.crypt.Verifier') as Verifier:
            Verifier.from_string = mock.MagicMock(name='from_string',
                                                  return_value=verifier)
            self.assertRaises(crypt.AppIdentityError, crypt._verify_signature,
                              message, signature, certs)

            # Make sure our mocks were called as expected.
            Verifier.from_string.assert_called_once_with(cert_value,
                                                         is_x509_cert=True)
            verifier.verify.assert_called_once_with(message, signature)


class Test__check_audience(unittest.TestCase):

    def test_null_audience(self):
        result = crypt._check_audience(None, None)
        self.assertEqual(result, None)

    def test_success(self):
        audience = 'audience'
        payload_dict = {'aud': audience}
        result = crypt._check_audience(payload_dict, audience)
        # No exception and no result.
        self.assertEqual(result, None)

    def test_missing_aud(self):
        audience = 'audience'
        payload_dict = {}
        self.assertRaises(crypt.AppIdentityError, crypt._check_audience,
                          payload_dict, audience)

    def test_wrong_aud(self):
        audience1 = 'audience1'
        audience2 = 'audience2'
        self.assertNotEqual(audience1, audience2)
        payload_dict = {'aud': audience1}
        self.assertRaises(crypt.AppIdentityError, crypt._check_audience,
                          payload_dict, audience2)


class _MockOrderedDict(object):

    def __init__(self, *values):
        self._values = values

    def values(self):
        return self._values
