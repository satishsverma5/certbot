"""Test for certbot_apache.http_01."""
import mock
import os
import unittest

from acme import challenges

from certbot import achallenges

from certbot.tests import acme_util

from certbot_apache.tests import util


NUM_ACHALLS = 3


class ApacheHttp01TestMeta(type):
    """Generates parmeterized tests for testing perform."""
    def __new__(mcs, name, bases, class_dict):

        def _gen_test(num_achalls, minor_version):
            def _test(self):
                achalls = self.achalls[:num_achalls]
                self.config.version = (2, minor_version)
                self.common_perform_test(achalls)
            return _test

        for i in range(1, NUM_ACHALLS + 1):
            for j in (2, 4):
                test_name = "test_perform_{0}_{1}".format(i, j)
                class_dict[test_name] = _gen_test(i, j)
        return type.__new__(mcs, name, bases, class_dict)


class ApacheHttp01Test(util.ApacheTest):
    """Test for certbot_apache.http_01.ApacheHttp01."""

    __metaclass__ = ApacheHttp01TestMeta

    def setUp(self, *args, **kwargs):
        super(ApacheHttp01Test, self).setUp(*args, **kwargs)

        self.account_key = self.rsa512jwk
        self.achalls = []
        for i in range(NUM_ACHALLS):
            self.achalls.append(
                achallenges.KeyAuthorizationAnnotatedChallenge(
                    challb=acme_util.chall_to_challb(
                        challenges.HTTP01(token=((chr(ord('a') + i) * 16))),
                        "pending"),
                    domain="example{0}.com".format(i),
                    account_key=self.account_key))

        modules = ["alias", "authz_core", "authz_host"]
        for mod in modules:
            self.config.parser.modules.add("mod_{0}.c".format(mod))
            self.config.parser.modules.add(mod + "_module")

        from certbot_apache.http_01 import ApacheHttp01
        self.http = ApacheHttp01(self.config)

    def test_empty_perform(self):
        self.assertFalse(self.http.perform())

    @mock.patch("certbot_apache.configurator.ApacheConfigurator.enable_mod")
    def test_enable_modules_22(self, mock_enmod):
        self.config.version = (2, 2)
        self.config.parser.modules.remove("authz_host_module")
        self.config.parser.modules.remove("mod_authz_host.c")

        enmod_calls = self.common_enable_modules_test(mock_enmod)
        self.assertEqual(enmod_calls[0][0][0], "authz_host")

    @mock.patch("certbot_apache.configurator.ApacheConfigurator.enable_mod")
    def test_enable_modules_24(self, mock_enmod):
        self.config.parser.modules.remove("authz_core_module")
        self.config.parser.modules.remove("mod_authz_core.c")

        enmod_calls = self.common_enable_modules_test(mock_enmod)
        self.assertEqual(enmod_calls[0][0][0], "authz_core")

    def common_enable_modules_test(self, mock_enmod):
        """Tests enabling mod_alias and other modules."""
        self.config.parser.modules.remove("alias_module")
        self.config.parser.modules.remove("mod_alias.c")

        self.http.prepare_http01_modules()

        self.assertTrue(mock_enmod.called)
        calls = mock_enmod.call_args_list
        other_calls = []
        for call in calls:
            if "alias" != call[0][0]:
                other_calls.append(call)

        # If these lists are equal, we never enabled mod_alias
        self.assertNotEqual(calls, other_calls)
        return other_calls

    def common_perform_test(self, achalls):
        """Tests perform with the given achalls."""
        for achall in achalls:
            self.http.add_chall(achall)

        expected_response = [
            achall.response(self.account_key) for achall in achalls]
        self.assertEqual(self.http.perform(), expected_response)

        self.assertTrue(os.path.isdir(self.http.challenge_dir))
        self._has_min_permissions(self.http.challenge_dir, 0o755)
        self._test_challenge_conf()

        for achall in achalls:
            self._test_challenge_file(achall)

        challenge_dir = self.http.challenge_dir
        self.http.cleanup()
        self.assertFalse(os.path.exists(challenge_dir))

    def _test_challenge_conf(self):
        self.assertEqual(
            len(self.config.parser.find_dir(
                "Include", self.http.challenge_conf)), 1)

        with open(self.http.challenge_conf) as f:
            conf_contents = f.read()

        alias_fmt = "Alias /.well-known/acme-challenge {0}"
        alias = alias_fmt.format(self.http.challenge_dir)
        self.assertTrue(alias in conf_contents)
        if self.config.version < (2, 4):
            self.assertTrue("Allow from all" in conf_contents)
        else:
            self.assertTrue("Require all granted" in conf_contents)

    def _test_challenge_file(self, achall):
        name = os.path.join(self.http.challenge_dir, achall.chall.encode("token"))
        validation = achall.validation(self.account_key)

        self._has_min_permissions(name, 0o644)
        with open(name, 'rb') as f:
            self.assertEqual(f.read(), validation.encode())

    def _has_min_permissions(self, path, min_mode):
        """Tests the given file has at least the permissions in mode."""
        st_mode = os.stat(path).st_mode
        self.assertEqual(st_mode, st_mode | min_mode)


if __name__ == "__main__":
    unittest.main()  # pragma: no cover
