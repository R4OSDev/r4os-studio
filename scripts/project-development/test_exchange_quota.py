import unittest

from contracts import DevelopmentFault
from exchange import preflight, require_tree
from exchange_policy import EXCHANGE_LIMITS


class ExchangeQuotaTests(unittest.TestCase):
    def test_larger_worker_required_before_guest_writes(self):
        for worker in ({'buildTreeVersion': 1}, {'buildTreeVersion': 1,
                'limits': {'files': 128, 'bytes': 96 * 1024 * 1024, 'directories': 128, 'depth': 6}},
                {'buildTreeVersion': 1, 'limits': {**EXCHANGE_LIMITS, 'depth': 6}}):
            with self.assertRaises(DevelopmentFault) as result:
                require_tree({'exchangeWorker': worker})
            self.assertEqual(result.exception.reason_code, 'exchange_worker_upgrade_required')
        require_tree({'exchangeWorker': {'buildTreeVersion': 1, 'limits': EXCHANGE_LIMITS}})

    def test_previous_failure_fits_and_staging_still_cannot_exceed_capacity(self):
        # The actual failed workload had 123 files, 24 folders and ~3.3 MiB.
        entries = [{'directory': False, 'bytes': 28000} for _ in range(123)]
        entries += [{'directory': True, 'bytes': 0} for _ in range(24)]
        preflight(entries, [74971, 159643, 12550], 5, 1)
        required = 2 * 100000 + 32768
        boundary = [{'directory': False, 'bytes': EXCHANGE_LIMITS['bytes'] - required}]
        preflight(boundary, [100000], 5, 1)
        boundary[0]['bytes'] += 1
        with self.assertRaises(DevelopmentFault) as result:
            preflight(boundary, [100000], 5, 1)
        self.assertEqual(result.exception.reason_code, 'exchange_quota_exceeded')
        with self.assertRaises(DevelopmentFault):
            preflight([{'directory': False, 'bytes': 0}] * EXCHANGE_LIMITS['files'], [], 0, 0)


if __name__ == '__main__': unittest.main()
