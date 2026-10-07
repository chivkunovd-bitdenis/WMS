#!/usr/bin/env python3
"""Check that new tasks have filled acceptance documents, not whether they passed."""

import argparse
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

SCRIPT_PATH = "scripts/ci/check_task_documents.py"
CONTRACT_CORRECTIONS_DIR = "docs/reviews/contract-corrections"

# An exact-content allowlist, NOT a generic permission to edit fixture code.
# Each pair is the entire historical file, including assertions, test names,
# decorators, imports and control flow. Changing even one other byte is denied.
# New pairs require a process change with RED regressions and independent review.
FIXTURE_BLOB_PAIRS = {
    "wms662-confirmed-wait-pid-pair": (
        "WMS-662", "backend/tests/test_wms662_cancellation_lock_order.py",
        "596edfbd0a4b47c61556ffedf38e8c2488fc43f0",
        "bf7c850d9c7948ffd3b7cef5cbea9b3c1404923e",
    ),
    "wms517-uuid-before-rollback": (
        "WMS-517", "backend/tests/test_wms517_sales_contract.py",
        "a36ab064c9a70b8c3df472f176e4e5ba9d567fcb",
        "393cb668b7b7fb702f75d949ba41421a46f5676e",
    ),
    "wms517-explicit-sales-fixture": (
        "WMS-517", "backend/tests/test_wms517_sales_contract.py",
        "393cb668b7b7fb702f75d949ba41421a46f5676e",
        "b5ddcb3b42810902b05da09726222b7e500684cf",
    ),
    "wms663-uuid-before-expire": (
        "WMS-663", "backend/tests/test_wms663_customs_documents_contract.py",
        "5fb61d0c51a6b4f2d84f3b5bf17397f622059283",
        "4e1aff5a80445fa61b5697d60a26985427dfd28e",
    ),
    "wms663-exemplar-save-selector": (
        "WMS-663", "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx",
        "21baad5243f664aca69ff817407ea17e66f59155",
        "8548a75eb6963edcd5e3b3755e0a618d918f9f94",
    ),
    "wms663-close-accessible-selector": (
        "WMS-663", "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx",
        "8548a75eb6963edcd5e3b3755e0a618d918f9f94",
        "7b41916c43bf144d9fdeb7772d415bdf5535ff05",
    ),
    "wms663-complete-positive-status-fixtures": (
        "WMS-663", "backend/tests/test_wms663_customs_documents_contract.py",
        "4e1aff5a80445fa61b5697d60a26985427dfd28e",
        "c92c075ba9f375c578538b776207cdc6b8b56ab3",
    ),
    "wms663-known-no-documents-complete-requirements": (
        "WMS-663", "frontend/src/screens/v2/OzonDocumentsAbsence.required-orders.dom.test.tsx",
        "5a508673b78388e44c903fe503fd76f3e48a7cde",
        "d96fd44965a7f0b8806d87fe3d4f88243cad1f5e",
    ),
    "wms662-live-delivery-test-format": (
        "WMS-662", "backend/tests/test_wms662_live_delivery_substatuses.py",
        "a6fc67e70364b0c84e9d2d41d734cd5af1cd61b4",
        "cefb7d8ac635c3da443a6f623c2fef4a1ff75850",
    ),
    "wms662-batch-first-wait-pid-snapshot": (
        "WMS-662", "backend/tests/test_wms662_batch_handoff_lock_order.py",
        "eb2255ca93ac453af1117339aa6cc9aba07ee2a0",
        "03d744d54222dc6ee13014d1f378bf07e6eb4e8a",
    ),
}

# Published Sol high exact chains: fixed whole-file blobs, no generic exemption.
NIGHT_REVIEWED_FIXTURE_PAIRS = {'wms-658-reviewed-1-test_wms658_marking_import_contract.py': ('WMS-658',
                                                               'backend/tests/test_wms658_marking_import_contract.py',
                                                               '9661a123265f1ea75d084fbf1b6da13d34481856',
                                                               '0a267634279a868660cbc014c6312bbf4cfc7798'),
 'wms-658-reviewed-1-test_wms658_wb_honest_sign_contract.py': ('WMS-658',
                                                               'backend/tests/test_wms658_wb_honest_sign_contract.py',
                                                               '9bf03cba6847065ee8b59030aece6f1695b4d22d',
                                                               '946ec81ef52d7fb888379b327dcd74be8ce52a99'),
 'wms-658-reviewed-2-test_wms658_marking_import_contract.py': ('WMS-658',
                                                               'backend/tests/test_wms658_marking_import_contract.py',
                                                               '0a267634279a868660cbc014c6312bbf4cfc7798',
                                                               'ff481b1e693884c103e46624a05807f3120bc040'),
 'wms-658-reviewed-3-test_wms658_marking_import_contract.py': ('WMS-658',
                                                               'backend/tests/test_wms658_marking_import_contract.py',
                                                               'ff481b1e693884c103e46624a05807f3120bc040',
                                                               'cee12538b9d752f040edcc2c7a892726d307d68d'),
 'wms-658-reviewed-4-test_wms658_marking_import_contract.py': ('WMS-658',
                                                               'backend/tests/test_wms658_marking_import_contract.py',
                                                               'cee12538b9d752f040edcc2c7a892726d307d68d',
                                                               '6e76bf1d4bcf38ff59341e6d3459346313421e6c'),
 'wms-681-reviewed-1-test_fbs_packing_box.py': ('WMS-681',
                                                'backend/tests/test_fbs_packing_box.py',
                                                '7f3d8754f68c2da1fd96ecdfb21f92ce1a6297c3',
                                                'bf92738de529c1ca4882240a0b617df5db82dedd'),
 'wms-681-reviewed-1-FfFbsSupplyWorkspace.assembly.dom.test.tsx': ('WMS-681',
                                                                   'frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx',
                                                                   'c6647a611da4d6f92d9afe0c3cd8990a0c7b9fc4',
                                                                   'c809482c9eb151425e9031e33b06246cb1e6039a'),
 'wms-681-reviewed-2-test_fbs_packing_box.py': ('WMS-681',
                                                'backend/tests/test_fbs_packing_box.py',
                                                'bf92738de529c1ca4882240a0b617df5db82dedd',
                                                '1cca9c86a4e50842919d0ca4aec4c57607c0fe7a'),
 'wms-681-reviewed-2-FfFbsSupplyWorkspace.assembly.dom.test.tsx': ('WMS-681',
                                                                   'frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx',
                                                                   'c809482c9eb151425e9031e33b06246cb1e6039a',
                                                                   '58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3')}
NIGHT_REVIEWED_COMPANIONS = {'wms-658-reviewed-1-test_wms658_marking_import_contract.py': [{'path': 'docs/requirements/WMS-658.md',
                                                                'before_blob': '88a79ede1de989790d4cf814d208f3615420740f',
                                                                'after_blob': 'a1625ab8ba3c943cb7d8b7ed89c1db67f777eb58'}],
 'wms-658-reviewed-1-test_wms658_wb_honest_sign_contract.py': [{'path': 'docs/requirements/WMS-658.md',
                                                                'before_blob': '88a79ede1de989790d4cf814d208f3615420740f',
                                                                'after_blob': 'a1625ab8ba3c943cb7d8b7ed89c1db67f777eb58'}]}
NIGHT_REVIEWED_FIXTURE_PAIRS["wms681-integration-assembly-qr-recovery"] = (
    "WMS-681", "frontend/src/screens/v2/FfFbsSupplyWorkspace.assembly.dom.test.tsx",
    "58e64cc04d11be4fd7ad25b5fcb93bfb254d99f3",
    "12358c8953c842819db9a1b277ce51cbd83b9915",
)
FIXTURE_BLOB_PAIRS.update(NIGHT_REVIEWED_FIXTURE_PAIRS)

POSITIVE_STATUS_TRANSFORM = "wms663-complete-positive-status-fixtures"
POSITIVE_STATUS_HANDOFF = (
    "docs/reviews/wms663-healthy-positive-fixture-correction-handoff.md",
    "75319cb7026d032af7e47946b4b636aadc39c8eb",
)
LEGACY_SALES_COMPANION = {
    "path": "backend/tests/test_withdrawal_ledger.py",
    "before_blob": "d7f0d01d0f417aea487d0d7f616ba240b133f5a4",
    "after_blob": "a7ba000fd763b978784d0a5b6f4120df188c3084",
}

# Owner-authorized semantic changes are NOT fixture corrections. Immutable pins
# name the entire historical UI file and every allowed published transition.
OWNER_UI_SUPERSESSIONS = {
    "WMS-662": {
        "source_commit": "585877bedf948faf7e38d14acc7e89acbf4feab3",
        "contract_commit": "2006171f0feae5513f887b471125ecae1a96c2ae",
        "prior_commit": "2006171f0feae5513f887b471125ecae1a96c2ae",
        "path": "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms662.c19.dom.test.tsx",
        "before_blob": "04379c221c29e9a70ae195ff3d834e1855b375de",
        "changes": [["667a136a2760ff62fc181f47772290a8388587c6", "eda2d0d82663c76a3042e3a161fb47f164ad4f08"]],
    },
    "WMS-663": {
        "source_commit": "585877bedf948faf7e38d14acc7e89acbf4feab3",
        "contract_commit": "ae2ebd3d17f4e7364b1b52de4126b8f70937652b",
        "prior_commit": "d9e022697e098a2f9c0feee6a5bf03f99cac5945",
        "path": "frontend/src/screens/v2/FfFbsSupplyWorkspace.wms663.dom.test.tsx",
        "before_blob": "7b41916c43bf144d9fdeb7772d415bdf5535ff05",
        "changes": [
            ["35ac50caa77f1ca5eb1905a23a730e1dee1e2f45", "87d14b74cbfa4f7f119bb0c6374929259fed5dc5"],
            ["23b222dede4869ae6035c55175f5d14f6a6af5f4", "e177548bb5a728cad63b32528071c1c5ac9995e1"],
        ],
    },
}
OWNER_UI_REQUEST = {
    "commit": "4c9e1238c85a50a9238bc109651c79cac5f10e03",
    "path": "docs/reviews/wms663-666-frontend-rollback-scope-20261006.md",
    "blob": "664aa8ea5e279c04f9b6219a8440142fd7bc142a",
}


# One reviewed owner-supersession chain, immutable published Git objects.
WMS680_CLOSED_CHAIN = {'reviewed_source_commit': '535e8a970928e8834147553ad4c0139fcc5f10da',
 'original_contract': '24009478c3a58b558ad8a661d83dc5920108cb00',
 'final_correction_commit': '535e8a970928e8834147553ad4c0139fcc5f10da',
 'report': {'path': 'docs/reviews/WMS-652-final-night-release-review-20261007.md',
            'commit': 'da5b0db7ad48bc6a3f7b7d51371185b133554ce6',
            'blob': '7f24a11ee73ea224ee37e9f86161212fe786b8a6'},
 'owner': {'source': '7015448e255f606ef74b69e04e81f53777a099d5',
           'correction': '3be84bb091712caa2e32226f989e3008e47618a5',
           'artifacts': {'docs/evidence/WMS-680/acceptance-20261007/baseline-source.json': [None,
                                                                                            '2d399ace6c00df72c28843d7e0802687a089e632'],
                         'docs/evidence/WMS-680/acceptance-20261007/fbo-ozon-long-before-columns.html': [None,
                                                                                                         'b507fdd97763f9227137321f32c0b4d5696e984b'],
                         'docs/evidence/WMS-680/acceptance-20261007/fbo-wb-normal-before-columns.html': [None,
                                                                                                         'c9a1711a963b8ec88b38ea26fad7f337705888a9'],
                         'docs/requirements/WMS-680.md': ['aad7a41a3ea194fdcf2eb596643a30a0096ac488',
                                                          'b765c124dc7641ea83a6347fe4b1cc50e648ec4d']}},
 'contracts': {'24009478c3a58b558ad8a661d83dc5920108cb00': {'backend/tests/test_wms680_print_payload_contract.py': ['f7510d80221621aa192dacfe0fd0f7837a18385e',
                                                                                                                    'f7510d80221621aa192dacfe0fd0f7837a18385e'],
                                                            'frontend/src/utils/wms680PrintContract.test.ts': ['c8847911821967052947bd9f90691892188193e1',
                                                                                                               '799f895bb38acca23867042e7b31c6cba96e7884']},
               '5739ed2ea900b8d6ddc8a9326bf1dc07e687fd8e': {'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts': ['ab978dfabfb1f41076e0a16666e94fa081f3ec21',
                                                                                                                           '299ff644942016a7cee5ee665cbc321ebddbddbc'],
                                                            'frontend/src/utils/printInboundReceivingSheet.test.ts': ['c4cc01c1726331f4ee5f912606017638ba6aea76',
                                                                                                                      'c4cc01c1726331f4ee5f912606017638ba6aea76'],
                                                            'frontend/src/utils/printShipmentPackagingSheet.test.ts': ['f59bd4972d9c4a716263b24ab417c74c80377888',
                                                                                                                       'f59bd4972d9c4a716263b24ab417c74c80377888'],
                                                            'frontend/src/utils/wms680PrintContract.test.ts': ['f3b12dd1617453a445a5624e19c19692c70a4693',
                                                                                                               '799f895bb38acca23867042e7b31c6cba96e7884'],
                                                            'frontend/src/utils/wms680PrintGeometry.test.ts': ['11ec2e43dcf3b696288bcaa55d6cd83a454858d8',
                                                                                                               '81a83b3794340eadd60abba94594d6ff09d533ae']},
               '739bcadf1be4fe92e24af3d30b42f892f858e598': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['34f4ef6ca82d72cf65583d6ba6bdcefb689128a6',
                                                                                                               '81a83b3794340eadd60abba94594d6ff09d533ae']}},
 'steps': [{'kind': 'owner_ui_supersession',
            'source': '8baaa27bf91851327ba30d6e93b29fbfb5c423fd',
            'correction': '5739ed2ea900b8d6ddc8a9326bf1dc07e687fd8e',
            'files': {'frontend/src/utils/wms680PrintContract.test.ts': ['c8847911821967052947bd9f90691892188193e1',
                                                                         'f3b12dd1617453a445a5624e19c19692c70a4693'],
                      'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts': ['f01723a9ccee9cc4466797875c9d16a79f50a608',
                                                                                     'ab978dfabfb1f41076e0a16666e94fa081f3ec21'],
                      'frontend/src/utils/wms680PrintGeometry.test.ts': [None,
                                                                         '11ec2e43dcf3b696288bcaa55d6cd83a454858d8']}},
           {'kind': 'exact_fixture_correction',
            'transform': 'wms680-size-zero-exact-cells',
            'source': '1d335e8aead87fc27895a9577253cb8abdf9ca5a',
            'correction': '7ad0aa781d175ef7f4e1d16074a12b47eed655f2',
            'files': {'frontend/src/utils/wms680PrintContract.test.ts': ['f3b12dd1617453a445a5624e19c19692c70a4693',
                                                                         '799f895bb38acca23867042e7b31c6cba96e7884']}},
           {'kind': 'exact_fixture_correction',
            'transform': 'wms680-product-anchor',
            'source': 'e8638be207559fee31a069734026cda1d4fcccb4',
            'correction': '11806bd237c48a030a4e0ff49bb12dd90dfe6778',
            'files': {'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts': ['ab978dfabfb1f41076e0a16666e94fa081f3ec21',
                                                                                     '299ff644942016a7cee5ee665cbc321ebddbddbc']}},
           {'kind': 'exact_fixture_correction',
            'transform': 'wms680-safe-filenames',
            'source': '363e3b58110c61283f44cbb0cfdba5ee227de9aa',
            'correction': '739bcadf1be4fe92e24af3d30b42f892f858e598',
            'files': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['11ec2e43dcf3b696288bcaa55d6cd83a454858d8',
                                                                         '34f4ef6ca82d72cf65583d6ba6bdcefb689128a6']}},
           {'kind': 'additive_bug_coverage',
            'transform': 'wms680-numeric-subtable',
            'source': '739bcadf1be4fe92e24af3d30b42f892f858e598',
            'parent': 'd300851544c9587d6563462c23a60c3b67d1af12',
            'correction': 'f2de20008df3b21c1decead0e1051dbda4a4a08a',
            'model': 'gpt-6.1-sol',
            'effort': 'high',
            'files': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['34f4ef6ca82d72cf65583d6ba6bdcefb689128a6',
                                                                         '0c7cc8f9f06fad5df0f7f3bd924dde607179a068']}},
           {'kind': 'exact_fixture_correction',
            'transform': 'wms680-linux-wrapped-text-and-browser-exit',
            'source': '0df92673934df8768efabe470baeca6f2f4568af',
            'correction': '4ed0c391135c95b67879c954195034b9c43d4980',
            'files': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['0c7cc8f9f06fad5df0f7f3bd924dde607179a068',
                                                                         '00162dc5c08858803c5a988c75328dab0f00cfdc']}},
           {'kind': 'exact_fixture_correction',
            'transform': 'wms680-real-pdf-cell-isolation',
            'source': '58fb2f240e83f997ee79e87ba1e0dd6cb76ef982',
            'correction': '535e8a970928e8834147553ad4c0139fcc5f10da',
            'files': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['00162dc5c08858803c5a988c75328dab0f00cfdc',
                                                                         '81a83b3794340eadd60abba94594d6ff09d533ae']}}]}
WMS680_CLOSED_SCOPES = {'3be84bb091712caa2e32226f989e3008e47618a5': {'docs/evidence/WMS-680/acceptance-20261007/baseline-source.json': (None,
                                                                                                                 '2d399ace6c00df72c28843d7e0802687a089e632'),
                                              'docs/evidence/WMS-680/acceptance-20261007/fbo-ozon-long-before-columns.html': (None,
                                                                                                                              'b507fdd97763f9227137321f32c0b4d5696e984b'),
                                              'docs/evidence/WMS-680/acceptance-20261007/fbo-wb-normal-before-columns.html': (None,
                                                                                                                              'c9a1711a963b8ec88b38ea26fad7f337705888a9'),
                                              'docs/requirements/WMS-680.md': ('aad7a41a3ea194fdcf2eb596643a30a0096ac488',
                                                                               'b765c124dc7641ea83a6347fe4b1cc50e648ec4d')},
 '5739ed2ea900b8d6ddc8a9326bf1dc07e687fd8e': {'docs/requirements/WMS-680.md': ('b765c124dc7641ea83a6347fe4b1cc50e648ec4d',
                                                                               '20fcef00da292c0a1a0cec6a100bfb8a0e4e464e'),
                                              'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts': ('f01723a9ccee9cc4466797875c9d16a79f50a608',
                                                                                                             'ab978dfabfb1f41076e0a16666e94fa081f3ec21'),
                                              'frontend/src/utils/printInboundReceivingSheet.test.ts': ('e71e18dddc41804c8cbf370362e58bd11154ea04',
                                                                                                        'c4cc01c1726331f4ee5f912606017638ba6aea76'),
                                              'frontend/src/utils/printShipmentPackagingSheet.test.ts': ('9a11e5b4b88fe257622865dd0e0fb15c9083cf2e',
                                                                                                         'f59bd4972d9c4a716263b24ab417c74c80377888'),
                                              'frontend/src/utils/wms680PrintContract.test.ts': ('c8847911821967052947bd9f90691892188193e1',
                                                                                                 'f3b12dd1617453a445a5624e19c19692c70a4693'),
                                              'frontend/src/utils/wms680PrintGeometry.test.ts': (None,
                                                                                                 '11ec2e43dcf3b696288bcaa55d6cd83a454858d8')},
 '7ad0aa781d175ef7f4e1d16074a12b47eed655f2': {'frontend/src/utils/wms680PrintContract.test.ts': ('f3b12dd1617453a445a5624e19c19692c70a4693',
                                                                                                 '799f895bb38acca23867042e7b31c6cba96e7884')},
 '11806bd237c48a030a4e0ff49bb12dd90dfe6778': {'frontend/src/screens/v2/fbsPickingListPrint.wms657.test.ts': ('ab978dfabfb1f41076e0a16666e94fa081f3ec21',
                                                                                                             '299ff644942016a7cee5ee665cbc321ebddbddbc')},
 '739bcadf1be4fe92e24af3d30b42f892f858e598': {'frontend/src/utils/wms680PrintGeometry.test.ts': ('11ec2e43dcf3b696288bcaa55d6cd83a454858d8',
                                                                                                 '34f4ef6ca82d72cf65583d6ba6bdcefb689128a6')},
 'f2de20008df3b21c1decead0e1051dbda4a4a08a': {'frontend/src/utils/wms680PrintGeometry.test.ts': ('34f4ef6ca82d72cf65583d6ba6bdcefb689128a6',
                                                                                                 '0c7cc8f9f06fad5df0f7f3bd924dde607179a068')},
 '4ed0c391135c95b67879c954195034b9c43d4980': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['0c7cc8f9f06fad5df0f7f3bd924dde607179a068',
                                                                                                 '00162dc5c08858803c5a988c75328dab0f00cfdc']},
 '535e8a970928e8834147553ad4c0139fcc5f10da': {'frontend/src/utils/wms680PrintGeometry.test.ts': ['00162dc5c08858803c5a988c75328dab0f00cfdc',
                                                                                                 '81a83b3794340eadd60abba94594d6ff09d533ae']}}

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def task_refs(root: Path, base: str) -> list[str]:
    # Old commits in a long-lived PR must not acquire retrospective obligations.
    introductions = git(root, "log", "--diff-filter=A", "--format=%H", "HEAD",
                        "--", SCRIPT_PATH).splitlines()
    refs = set()
    for commit in git(root, "rev-list", f"{base}..HEAD").splitlines():
        if not any(subprocess.run(
            ["git", "merge-base", "--is-ancestor", start, commit], cwd=root,
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0 for start in introductions):
            continue
        refs.update(re.findall(r"\bWMS-\d+\b", git(root, "show", "-s", "--format=%B", commit)))
    return sorted(refs)


def visible_lines(text: str) -> list[str]:
    """Ignore examples inside fenced code blocks."""
    lines = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = ""
            continue
        if marker:
            fence = marker[1]
        else:
            lines.append(line)
    return lines


def cells(line: str) -> list[str]:
    line = line.strip().removeprefix("|").removesuffix("|")
    return [part.strip() for part in re.split(r"(?<!\\)\|", line)]


def plain(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(str.maketrans("", "", "*_`"))).strip()


def test_reference(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(str.maketrans("", "", "*`"))).strip()


def test_references(value: str) -> list[str]:
    """Validate every test link stored in one Markdown table cell."""
    return [
        reference
        for part in re.split(r"<br\s*/?>", value, flags=re.IGNORECASE)
        if (reference := test_reference(part))
    ]


def test_reference_errors(root: Path, reference: str) -> list[str]:
    path_text, separator, test_name = test_reference(reference).partition("::")
    pure = PurePosixPath(path_text)
    if (
        not separator
        or not path_text
        or not test_name
        or pure.is_absolute()
        or str(pure) != path_text
        or ".." in pure.parts
    ):
        return [f"Некорректная ссылка на тест: {reference}; ожидается путь::имя теста."]
    path = root / path_text
    if not path.is_file():
        return [f"Нет файла теста {path_text}."]
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [f"Файл теста {path_text} не является текстовым."]
    # Exact saved original/hash/case/report proof also covers it.each expansion.
    # Unprotected legacy references still use the literal source contract.
    import sys
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from scripts.ci.promote_guards import saved_process_policy, verify_registered_case
    try:
        policy = (saved_process_policy(root)
                  if (root / "guards/PROCESS_CONTRACTS.json").exists()
                  or (root / "guards/PROCESS_CONTRACTS.json").is_symlink() else None)
        if policy is not None and path_text in policy["files"]:
            if verify_registered_case(root, policy, pure, test_name):
                return []
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        return [f"Не подтверждена постоянная охрана {path_text}::{test_name}: {exc}"]
    if test_name not in content:
        return [f"В {path_text} не найдено имя теста {test_name}."]
    return []


def document_errors(text: str, root: Path | None = None) -> list[str]:
    lines = visible_lines(text)
    errors = []
    checks = 0
    for i, line in enumerate(lines[:-1]):
        headers = [plain(cell).casefold() for cell in cells(line)]
        check_names = {"проверка", "сценарий", "check", "scenario"}
        verdict_names = {"вердикт", "результат", "результат проверки", "verdict"}
        if not check_names.intersection(headers) or not verdict_names.intersection(headers):
            continue
        separator = cells(lines[i + 1])
        if len(separator) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
            errors.append("У таблицы проверок нет корректной строки разделителей Markdown.")
            continue
        check_col = next(j for j, header in enumerate(headers) if header in check_names)
        verdict_col = next(j for j, header in enumerate(headers) if header in verdict_names)
        class_col = headers.index("класс") if "класс" in headers else None
        test_col = headers.index("тест") if "тест" in headers else None
        if class_col is not None and test_col is None:
            errors.append("В таблице с колонкой «Класс» нет колонки «Тест».")
        for row in lines[i + 2:]:
            if "|" not in row or not row.strip():
                break
            values = cells(row)
            checks += 1
            if len(values) != len(headers):
                errors.append(f"Неверное число ячеек в проверке: {row.strip()}")
                continue
            if not plain(values[check_col]):
                errors.append("В таблице есть проверка без описания или названия.")
            if not plain(values[verdict_col]):
                errors.append(f"Нет вердикта у проверки: {values[check_col]}")
            if class_col is not None and test_col is not None:
                check_class = plain(values[class_col]).casefold()
                references = test_references(values[test_col])
                if check_class in {"навсегда", "разово"}:
                    if not references:
                        errors.append(
                            f"У автоматической проверки {values[check_col]} нет ссылки на тест."
                        )
                    elif root is not None:
                        for reference in references:
                            errors.extend(test_reference_errors(root, reference))
    if not checks:
        errors.append("Нет проверок в таблице с колонками «Проверка» и «Вердикт».")

    conclusion = False
    for i, line in enumerate(lines):
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not heading:
            continue
        title = re.sub(r"^\d+[.)]\s*", "", plain(heading[2])).casefold()
        if title not in {"заключение", "итоговое заключение", "conclusion"}:
            continue
        for following in lines[i + 1:]:
            next_heading = re.match(r"^\s{0,3}(#{1,6})\s+", following)
            if next_heading:
                if len(next_heading[1]) <= len(heading[1]):
                    break
                continue
            if plain(following):
                conclusion = True
                break
    if not conclusion:
        errors.append("Не заполнен раздел «Заключение».")
    return errors


def commit_changed_paths(root: Path, commit: str) -> set[str]:
    revision = git(root, "rev-list", "--parents", "-n", "1", commit).split()
    if len(revision) == 1:
        return set(git(root, "ls-tree", "-r", "--name-only", commit).splitlines())
    return set(
        git(root, "diff", "--no-renames", "--name-only", revision[1], commit).splitlines()
    )


def is_task_contract_commit(root: Path, commit: str, task_id: str) -> bool:
    """Return whether commit is this task's real contract in current history."""
    exists = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0
    if not exists:
        return False
    if git(root, "show", "-s", "--format=%s", commit) != f"{task_id}: контракт тестов":
        return False
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def git_blob(root: Path, commit: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "ls-tree", "-z", "--full-tree", commit, "--", path], cwd=root,
        check=False, capture_output=True, text=True,
    )
    if result.returncode != 0 or "\t" not in result.stdout:
        return None
    metadata, found_path = result.stdout.removesuffix("\0").split("\t", 1)
    fields = metadata.split()
    # A matching blob in a symlink, executable or gitlink is not this test file.
    if len(fields) != 3 or fields[:2] != ["100644", "blob"] or found_path != path:
        return None
    return fields[2]


def ancestor(root: Path, older: str, newer: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
        check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0


def exact_fixture_corrections(
    root: Path, task_id: str, contract_commit: str, ledger: dict,
    superseded: dict[tuple[str, str], str] | None = None,
) -> tuple[dict[str, set[str]], list[str]]:
    """Validate an explicit, exact-content chain without relaxing legacy rules.

    The committed ledger binds each independent review to one exact source and
    correction. Git facts and artifacts are checked here; obtaining a real
    independent Astra high verdict remains the controller's responsibility.
    Companions prove the whole correction commit's scope but are not silently
    promoted into frozen business contracts.
    """
    def fail(reason: str) -> tuple[dict[str, set[str]], list[str]]:
        return {}, [f"{task_id}: fixture-only: {reason}"]

    head = git(root, "rev-parse", "HEAD")
    entries = ledger.get("fixture_corrections")
    if (
        ledger.get("task") != task_id or not isinstance(entries, list) or not entries
        or any(key in ledger for key in (
            "corrections", "contract_commit", "correction_commit", "files", "review",
        ))
    ):
        return fail("неполный или смешанный формат")
    # Per original contract and file, track exact reviewed SHA and content.
    frontier: dict[str, dict[str, tuple[str, str]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return fail("запись должна быть объектом")
        original = entry.get("contract_commit")
        source = entry.get("source_commit")
        correction = entry.get("correction_commit")
        if any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
               for sha in (original, source, correction)):
            return fail("нужны полные SHA исходного контракта, источника и коррекции")
        if not is_task_contract_commit(root, original, task_id):
            return fail("неизвестный исходный контракт")
        if (source == correction or not ancestor(root, original, source)
                or not ancestor(root, source, correction)
                or not ancestor(root, correction, head)):
            return fail("неверная последовательность коммитов")
        parents = git(root, "rev-list", "--parents", "-n", "1", correction).split()
        if len(parents) != 2:
            return fail("коррекция должна быть обычным коммитом с одним родителем")
        parent = parents[1]
        frozen = {path for path in commit_changed_paths(root, original)
                  if not path.startswith("docs/requirements/")}
        if original not in frontier:
            originals = {path: git_blob(root, original, path) for path in frozen}
            if any(blob is None for blob in originals.values()):
                return fail("исходные frozen файлы должны быть обычными Git blob")
            frontier[original] = {path: (original, blob) for path, blob in originals.items()}
        state = frontier[original]
        files = entry.get("files")
        companions = entry.get("companion_files", [])
        if (not isinstance(files, list) or not files
                or not isinstance(companions, list)):
            return fail("нужны точные списки файлов")
        expected: set[str] = set()
        transforms = set()
        for item in files:
            if not isinstance(item, dict) or not isinstance(item.get("transform"), str):
                return fail("неверное описание преобразования")
            transform = item["transform"]
            allowed = FIXTURE_BLOB_PAIRS.get(transform)
            if allowed is None or allowed != (
                task_id, item.get("path"), item.get("before_blob"), item.get("after_blob"),
            ):
                return fail("неподдерживаемое преобразование или изменены frozen expectations")
            _, path, before, after = allowed
            if path not in frozen or path in expected:
                return fail("повторный или незамороженный файл")
            expected.add(path)
            transforms.add(transform)
            prior_sha, prior_blob = state.get(path, (original, git_blob(root, original, path)))
            # Only this reviewed fifth pair has a later product source. Reject
            # even a reverted intervening mutation, not merely differing bytes.
            source_matches = source == prior_sha
            if (transform == POSITIVE_STATUS_TRANSFORM or transform in NIGHT_REVIEWED_FIXTURE_PAIRS) and not source_matches:
                source_matches = ancestor(root, prior_sha, source) and not git(
                    root, "log", "--full-history", "--format=%H", f"{prior_sha}..{source}",
                    "--", path,
                )
            if (not source_matches or before != prior_blob
                    or git_blob(root, source, path) != before
                    or git_blob(root, parent, path) != before
                    or git_blob(root, correction, path) != after):
                return fail("подменён source/blob или пропущена дельта цепочки")
            state[path] = (correction, after)
        required_companions = ([LEGACY_SALES_COMPANION]
                               if "wms517-explicit-sales-fixture" in transforms else [])
        if transforms & NIGHT_REVIEWED_FIXTURE_PAIRS.keys():
            required_companions = []
            for transform in sorted(transforms):
                for companion in NIGHT_REVIEWED_COMPANIONS.get(transform, []):
                    if companion not in required_companions:
                        required_companions.append(companion)
        if companions != required_companions:
            return fail("неподдерживаемые дополнительные файлы")
        for companion in required_companions:
            path = companion["path"]
            if (path in expected or path in frozen
                    or git_blob(root, parent, path) != companion["before_blob"]
                    or git_blob(root, correction, path) != companion["after_blob"]):
                return fail("подменён точный companion blob")
            expected.add(path)
        if POSITIVE_STATUS_TRANSFORM in transforms:
            handoff_path, handoff_blob = POSITIVE_STATUS_HANDOFF
            if (git(root, "ls-tree", "-z", "--full-tree", parent, "--", handoff_path)
                    or git_blob(root, correction, handoff_path) != handoff_blob
                    or git_blob(root, head, handoff_path) != handoff_blob):
                return fail("подменён точный positive STATUS handoff")
            expected.add(handoff_path)
        if commit_changed_paths(root, correction) != expected:
            return fail("коммит меняет не ровно перечисленные файлы")
        review = entry.get("review")
        if (not isinstance(review, dict) or review.get("model") not in ("gpt-6-astra", "gpt-6.1-sol")
                or review.get("effort") != "high" or review.get("verdict") != "PASS"
                or review.get("source_commit") != source
                or review.get("correction_commit") != correction):
            return fail("нет отдельного разрешённого high PASS точной дельты")
        evidence_commit = review.get("evidence_commit")
        evidence_blob = review.get("evidence_blob")
        evidence = review.get("evidence")
        if (not isinstance(evidence_commit, str)
                or not re.fullmatch(r"[0-9a-f]{40}", evidence_commit)
                or not isinstance(evidence_blob, str)
                or not re.fullmatch(r"[0-9a-f]{40}", evidence_blob)
                or not isinstance(evidence, str)
                or not evidence.startswith("docs/reviews/")
                or not evidence.endswith(".md")
                or str(PurePosixPath(evidence)) != evidence
                or ".." in PurePosixPath(evidence).parts
                or correction == evidence_commit
                or not ancestor(root, correction, evidence_commit)
                or not ancestor(root, evidence_commit, head)
                or git_blob(root, evidence_commit, evidence) != evidence_blob
                or git_blob(root, head, evidence) != evidence_blob
                or evidence not in commit_changed_paths(root, evidence_commit)):
            return fail("нет неизменного отдельного review artifact в HEAD")
        # Historical reports sometimes spell an unambiguous 9-character SHA.
        evidence_text = git(root, "show", f"{evidence_commit}:{evidence}")
        if not any(correction.startswith(token)
                   for token in re.findall(r"\b[0-9a-f]{9,40}\b", evidence_text)):
            return fail("review artifact не называет проверенную коррекцию")
    baselines: dict[str, set[str]] = {}
    for original, state in frontier.items():
        for path, (sha, blob) in state.items():
            if git_blob(root, head, path) != blob and (superseded or {}).get((original, path)) != blob:
                return fail(f"последующая мутация HEAD: {path}")
            if original == contract_commit and sha != original:
                baselines.setdefault(sha, set()).add(path)
    if git(root, "rev-parse", "HEAD") != head:
        return fail("HEAD изменился во время проверки; нужен повтор на точном SHA")
    return baselines, []


def owner_ui_supersessions(root: Path, task_id: str, ledger: dict):
    """Bind one exact semantic UI supersession to owner and real review proofs."""
    entries = ledger.get("owner_supersessions", [])
    if entries == []:
        return {}, {}, []
    def fail(reason):
        return {}, {}, [f"{task_id}: owner-supersession: {reason}"]
    def unchanged_since(start, end, path, blob):
        # Inspect descendants, including merges, rather than unrelated branch
        # additions of the same historical blob during scoped integration.
        return all(git_blob(root, sha, path) == blob for sha in git(
            root, "rev-list", "--ancestry-path", f"{start}..{end}",
        ).splitlines())
    allowed = OWNER_UI_SUPERSESSIONS.get(task_id)
    if allowed is None or not isinstance(entries, list) or len(entries) != 1:
        return fail("нужна одна точно разрешённая запись")
    entry = entries[0]
    if not isinstance(entry, dict) or any(entry.get(key) != value for key, value in allowed.items()):
        return fail("не совпадают exact contract/path/blob/история")
    head = git(root, "rev-parse", "HEAD")
    original, prior, path = entry["contract_commit"], entry["prior_commit"], entry["path"]
    source = entry.get("source_commit")
    if (not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
            or not is_task_contract_commit(root, original, task_id)
            or path not in commit_changed_paths(root, original)
            or not ancestor(root, original, prior) or not ancestor(root, prior, source)
            or git_blob(root, prior, path) != entry["before_blob"]
            or git_blob(root, source, path) != entry["before_blob"]
            or not unchanged_since(prior, source, path, entry["before_blob"])):
        return fail("неверный исходный frontier или промежуточная мутация")
    owner = entry.get("owner_request")
    if (owner != OWNER_UI_REQUEST or not ancestor(root, owner["commit"], head)
            or git_blob(root, owner["commit"], owner["path"]) != owner["blob"]
            or git_blob(root, head, owner["path"]) != owner["blob"]):
        return fail("нет неизменного exact owner-request artifact")
    current, before = source, entry["before_blob"]
    for correction, after in entry["changes"]:
        if not ancestor(root, current, correction) or not ancestor(root, correction, head):
            return fail("точная коррекция отсутствует в истории HEAD")
        parents = git(root, "rev-list", "--parents", "-n", "1", correction).split()
        if (len(parents) != 2 or not ancestor(root, current, parents[1])
                or not unchanged_since(current, parents[1], path, before)
                or commit_changed_paths(root, correction) != {path}
                or git_blob(root, parents[1], path) != before
                or git_blob(root, correction, path) != after
                or not ancestor(root, correction, head)):
            return fail("неверная exact дельта или пропущенная мутация")
        current, before = correction, after
    if (git_blob(root, head, path) != before
            or not unchanged_since(current, head, path, before)):
        return fail("последующая мутация superseded файла")
    review = entry.get("review")
    if (not isinstance(review, dict) or review.get("model") != "gpt-6.1-sol"
            or review.get("effort") != "high" or review.get("verdict") != "PASS"
            or review.get("source_commit") != source
            or review.get("correction_commit") != current):
        return fail("нет фактического отдельного Sol6.1 high PASS exact дельты")
    evidence, evidence_commit, evidence_blob = (review.get(key) for key in (
        "evidence", "evidence_commit", "evidence_blob"))
    if (not isinstance(evidence, str) or not evidence.startswith("docs/reviews/")
            or not evidence.endswith(".md") or str(PurePosixPath(evidence)) != evidence
            or ".." in PurePosixPath(evidence).parts
            or any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
                   for sha in (evidence_commit, evidence_blob))
            or current == evidence_commit or not ancestor(root, current, evidence_commit)
            or not ancestor(root, evidence_commit, head)
            or evidence not in commit_changed_paths(root, evidence_commit)
            or git_blob(root, evidence_commit, evidence) != evidence_blob
            or git_blob(root, head, evidence) != evidence_blob):
        return fail("нет неизменного отдельного review artifact")
    evidence_text = git(root, "show", f"{evidence_commit}:{evidence}")
    if (current not in re.findall(r"\b[0-9a-f]{40}\b", evidence_text)
            or not re.search(r"\bPASS\b", evidence_text)):
        return fail("review artifact не называет PASS и полный final test SHA")
    if git(root, "rev-parse", "HEAD") != head:
        return fail("HEAD изменился во время проверки")
    return {original: (current, {path})}, {(original, path): entry["before_blob"]}, []


def requirement_test_links_only(root: Path, before: str, after: str, path: str) -> bool:
    """A reviewed companion may update links, never requirement semantics."""
    def masked(text: str) -> str:
        lines = text.splitlines()
        for index, line in enumerate(lines[:-1]):
            headers = [plain(value).casefold() for value in cells(line)]
            if "тест" not in headers:
                continue
            separator = cells(lines[index + 1])
            if len(separator) != len(headers) or not all(re.fullmatch(r":?-{3,}:?", v) for v in separator):
                continue
            test_col = headers.index("тест")
            for row in range(index + 2, len(lines)):
                if "|" not in lines[row] or not lines[row].strip():
                    break
                values = cells(lines[row])
                if len(values) != len(headers):
                    break
                values[test_col] = "<test-links>"
                lines[row] = "|".join(values)
        return "\n".join(lines)
    if git_blob(root, before, path) is None or git_blob(root, after, path) is None:
        return False
    return masked(git(root, "show", f"{before}:{path}")) == masked(git(root, "show", f"{after}:{path}"))


def correction_companions(root: Path, task_id: str, correction: str, frozen: set[str],
                          expected: set[str], entry: dict) -> bool:
    parents = git(root, "rev-list", "--parents", "-n", "1", correction).split()
    if len(parents) != 2 or any(git_blob(root, correction, path) is None for path in expected):
        return False
    companions = commit_changed_paths(root, correction) - expected
    # This is compatibility for the independently reviewed WMS-687 additive
    # correction, not a new general correction/migration permission.
    if companions and (
        task_id != "WMS-687"
        or expected != {"frontend/src/screens/ff/FfInboundRequestView.wms687.dom.test.tsx"}
        or not companions.issubset({
            "docs/requirements/WMS-687.md",
            "frontend/src/screens/ff/FfInboundRequestView.wms687.permission.test.ts",
            "frontend/src/screens/ff/FfInboundRequestView.wms687.regression.dom.test.tsx",
        })
    ):
        return False
    declared = entry.get("ancillary_files")
    if declared is not None and (
        not isinstance(declared, list) or any(not isinstance(p, str) for p in declared)
        or len(declared) != len(set(declared)) or set(declared) != companions
    ):
        return False
    for path in companions:
        if path in frozen:
            return False
        if path == f"docs/requirements/{task_id}.md":
            if not requirement_test_links_only(root, parents[1], correction, path):
                return False
            continue
        # Only newly added tests of this exact task can accompany a correction.
        # Existing/frozen files, product code and another task are never allowed.
        own_test = (
            (path.startswith("frontend/src/") and re.search(
                rf"\.wms{task_id[4:]}(?:\.|_)\S*\.test\.(?:ts|tsx)$", path, re.I))
            or (path.startswith("backend/tests/") and re.search(
                rf"/test_wms{task_id[4:]}(?:_|\.)[^/]*\.py$", path, re.I))
        )
        if (not own_test or git_blob(root, parents[1], path) is not None
                or git_blob(root, correction, path) is None):
            return False
    review = entry["review"]
    if companions and ("report" in review or "report_commit" in review):
        report, ref = review.get("report"), review.get("report_commit")
        if (not isinstance(report, str) or not report.startswith("docs/reviews/")
                or not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{40}", ref)
                or not ancestor(root, correction, ref) or not ancestor(root, ref, "HEAD")
                or git_blob(root, ref, report) is None
                or git_blob(root, ref, report) != git_blob(root, "HEAD", report)):
            return False
    return True


def wms680_closed_correction(root: Path, ledger: dict, contract_commit: str):
    """Validate only the published owner request and closed reviewed 680 graph."""
    def fail(reason):
        return {}, [f"WMS-680: reviewed-closed-chain: {reason}"]
    blob_cache = {}
    def blob(sha, file):
        key = (sha, file)
        if key not in blob_cache:
            blob_cache[key] = git_blob(root, sha, file)
        return blob_cache[key]
    record = WMS680_CLOSED_CHAIN
    semantic, report = record["steps"][0], record["report"]
    source = semantic["source"]
    path = "frontend/src/utils/wms680PrintContract.test.ts"
    before, after = semantic["files"][path]
    def review(source, correction):
        return {"model": "gpt-6.1-sol", "effort": "high", "verdict": "PASS",
                "source_commit": source, "correction_commit": correction,
                "evidence": report["path"], "evidence_commit": report["commit"],
                "evidence_blob": report["blob"]}
    owner_path = "docs/evidence/WMS-680/acceptance-20261007/baseline-source.json"
    owner = {"contract_commit": record["original_contract"],
             "prior_commit": record["original_contract"], "source_commit": source,
             "path": path, "before_blob": before,
             "changes": [[semantic["correction"], after]],
             "companion_files": [{"path": name, "before_blob": pair[0], "after_blob": pair[1]}
                                 for name, pair in semantic["files"].items() if name != path],
             "owner_request": {"commit": record["owner"]["correction"], "path": owner_path,
                               "blob": record["owner"]["artifacts"][owner_path][1]},
             "review": review(source, semantic["correction"])}
    entries = []
    for step in record["steps"][1:]:
        originals = [semantic["correction"]]
        if step["correction"] == record["final_correction_commit"]:
            originals.append(step["source"])
        for original in originals:
            entries.append({"contract_commit": original, "source_commit": step["source"],
                            "correction_commit": step["correction"],
                            "files": [{"transform": step["transform"], "path": name,
                                       "before_blob": pair[0], "after_blob": pair[1]}
                                      for name, pair in step["files"].items()],
                            "companion_files": [],
                            "review": review(step["source"], step["correction"])})
    expected = {"task": "WMS-680", "owner_supersessions": [owner], "fixture_corrections": entries}
    contracts = dict(record["contracts"])
    # Several fixed corrections are also saved test contracts. Their exact
    # newly frozen files need the same final protection, including f2de.
    final_versions = {file: pair[1] for paths in contracts.values() for file, pair in paths.items()}
    for step in record["steps"]:
        correction = step["correction"]
        if correction not in contracts and is_task_contract_commit(root, correction, "WMS-680"):
            contracts[correction] = {
                file: [pair[1], final_versions[file]]
                for file, pair in WMS680_CLOSED_SCOPES[correction].items()
                if not file.startswith("docs/requirements/")
            }
    if ledger != expected or contract_commit not in contracts:
        return fail("не совпадает точная запись source/owner/scope/review/blob/цепочки")
    head = git(root, "rev-parse", "HEAD")
    if (not ancestor(root, report["commit"], head)
            or blob(report["commit"], report["path"]) != report["blob"]
            or blob(head, report["path"]) != report["blob"]):
        return fail("подменён независимый review artifact")
    report_text = git(root, "show", f"{report['commit']}:{report['path']}")
    if record["final_correction_commit"] not in report_text or "PASS" not in report_text:
        return fail("review не подтверждает точный final SHA")
    for artifact, pair in record["owner"]["artifacts"].items():
        if (blob(record["owner"]["source"], artifact) != pair[0]
                or blob(record["owner"]["correction"], artifact) != pair[1]):
            return fail("подменён historical owner-request blob")
        if artifact.startswith("docs/evidence/") and blob(head, artifact) != pair[1]:
            return fail("подменён сохранённый owner-request artifact")
    for step in [record["owner"], *record["steps"]]:
        correction, source = step["correction"], step.get("parent", step["source"])
        parents = git(root, "rev-list", "--parents", "-n", "1", correction).split()
        expected_paths = WMS680_CLOSED_SCOPES[correction]
        if (parents != [correction, source] or not ancestor(root, correction, report["commit"])
                or commit_changed_paths(root, correction) != set(expected_paths)):
            return fail("не совпадает exact commit scope/родитель")
        for file, pair in expected_paths.items():
            if blob(source, file) != pair[0] or blob(correction, file) != pair[1]:
                return fail("не совпадает exact whole-file blob")
    baselines = {}
    for original, paths in contracts.items():
        if not is_task_contract_commit(root, original, "WMS-680"):
            return fail("нет сохранённого исходного контракта")
        for file, pair in paths.items():
            if blob(original, file) != pair[0] or blob(head, file) != pair[1]:
                return fail(f"последующая мутация frozen HEAD: {file}")
            allowed = {pair[0], pair[1]}
            for step in record["steps"]:
                if file in step["files"]:
                    allowed.update(step["files"][file])
            for row in git(root, "rev-list", "--parents", "--ancestry-path", f"{original}..{head}").splitlines():
                sha, *parents = row.split()
                current = blob(sha, file)
                if current not in allowed:
                    return fail(f"непроверенная промежуточная мутация: {file}")
                if sha not in WMS680_CLOSED_SCOPES and current not in {
                        blob(parent, file) for parent in parents}:
                    return fail(f"непроверенная дельта frozen файла: {file}")
            if original == contract_commit and pair[0] != pair[1]:
                final = next(step["correction"] for step in reversed(record["steps"])
                             if step["files"].get(file, [None, None])[1] == pair[1])
                baselines.setdefault(final, set()).add(file)
    if git(root, "rev-parse", "HEAD") != head:
        return fail("HEAD изменился во время проверки")
    return baselines, []


def reviewed_contract_correction(
    root: Path,
    task_id: str,
    contract_commit: str,
) -> tuple[dict[str, set[str]], list[str]]:
    """Return independent correction baselines, or explain an invalid ledger.

    A correction is deliberately stricter than an ordinary follow-up commit: it
    may touch only files frozen by the original contract and must have a separate
    machine-readable ledger recording the independent approved-model high PASS. CI can
    validate the Git facts; the controller remains responsible for obtaining
    and recording the review before the ledger is committed.
    """
    ledger_rel = f"{CONTRACT_CORRECTIONS_DIR}/{task_id}.json"
    ledger_result = subprocess.run(
        ["git", "show", f"HEAD:{ledger_rel}"], cwd=root, check=False,
        capture_output=True, text=True,
    )
    if ledger_result.returncode != 0:
        return {}, []
    ledger_text = ledger_result.stdout.strip()
    try:
        ledger = json.loads(ledger_text)
    except json.JSONDecodeError:
        return {}, [
            f"{task_id}: некорректный реестр коррекции контракта {ledger_rel}"
        ]
    if not isinstance(ledger, dict):
        return {}, [
            f"{task_id}: реестр коррекции контракта должен быть JSON-объектом"
        ]
    if task_id == "WMS-680":
        return wms680_closed_correction(root, ledger, contract_commit)
    owner_baselines, owner_frontier, owner_errors = owner_ui_supersessions(root, task_id, ledger)
    if owner_errors:
        return {}, owner_errors
    def include_owner(baselines):
        override = owner_baselines.get(contract_commit)
        if override:
            final, paths = override
            baselines = {sha: files - paths for sha, files in baselines.items() if files - paths}
            baselines[final] = paths
        return baselines
    if "fixture_corrections" in ledger:
        baselines, errors = exact_fixture_corrections(root, task_id, contract_commit, ledger, owner_frontier)
        return (include_owner(baselines), []) if not errors else ({}, errors)
    incomplete = [
        f"{task_id}: реестр коррекции контракта заполнен не полностью"
    ]
    if ledger.get("task") != task_id:
        return {}, incomplete
    array_format = "corrections" in ledger
    if array_format:
        entries = ledger["corrections"]
        if (
            not isinstance(entries, list) or not entries
            or any(key in ledger for key in ("contract_commit", "correction_commit", "files", "review"))
        ):
            return {}, incomplete
    else:
        entries = [ledger]

    baselines: dict[str, set[str]] = {}
    corrected_by_contract: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            return {}, incomplete
        original = str(entry.get("contract_commit") or "")
        correction = str(entry.get("correction_commit") or "")
        files = entry.get("files")
        review = entry.get("review")
        if (
            not re.fullmatch(r"[0-9a-f]{40}", original)
            or not re.fullmatch(r"[0-9a-f]{40}", correction)
            or not isinstance(files, list) or not files
            or any(not isinstance(path, str) or not path for path in files)
            or len(files) != len(set(files))
            or not isinstance(review, dict)
            or review.get("model") not in ("gpt-6-astra", "gpt-6.1-sol")
            or review.get("effort") != "high"
            or review.get("verdict") != "PASS"
        ):
            return {}, incomplete
        # Validate every entry, even when its original is before the CI range.
        # A second contract for the task must not hide an invented source or
        # an invalid correction of the first contract.
        if not is_task_contract_commit(root, original, task_id):
            return {}, [f"{task_id}: реестр ссылается на неизвестный исходный контракт"]
        if correction == original:
            return {}, [f"{task_id}: коррекция должна быть отдельным последующим коммитом"]
        for older, newer, label in (
            (original, correction, "коррекция не следует за исходным контрактом"),
            (correction, "HEAD", "коррекция отсутствует в текущей версии"),
        ):
            if subprocess.run(
                ["git", "merge-base", "--is-ancestor", older, newer], cwd=root,
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ).returncode != 0:
                return {}, [f"{task_id}: {label}"]
        expected = set(files)
        frozen = {
            path for path in commit_changed_paths(root, original)
            if not path.startswith("docs/requirements/")
        }
        # Preserve the historical single-file legacy ledger only. New array
        # entries must always be strict subsets of their original contract.
        if not expected.issubset(frozen) or (
            expected == frozen and (array_format or len(frozen) > 1)
        ):
            return {}, [f"{task_id}: коррекция должна менять только часть исходного контракта"]
        if not correction_companions(root, task_id, correction, frozen, expected, entry):
            return {}, [f"{task_id}: коммит коррекции должен менять ровно перечисленные файлы"]
        already_corrected = corrected_by_contract.setdefault(original, set())
        if already_corrected & expected:
            return {}, [f"{task_id}: файлы коррекций одного контракта пересекаются"]
        already_corrected.update(expected)
        if original == contract_commit:
            baselines.setdefault(correction, set()).update(expected)
    return include_owner(baselines), []


def contract_change_errors(root: Path, base: str) -> list[str]:
    # Сравниваем содержимое файлов контракта в его коммите и в HEAD, а не пути
    # каждого последующего коммита: на pull_request HEAD — служебный merge-коммит
    # PR, его diff к первому родителю содержит весь PR, и контракт ложно считался
    # изменённым. Документ требований входит в коммит контракта (столбец «Тест»),
    # но вердикты и заключение в нём по процессу заполняет аналитик на приёмке,
    # поэтому он не замораживается.
    commits = git(root, "rev-list", "--reverse", f"{base}..HEAD").splitlines()
    errors = []
    contracts = []
    for commit in commits:
        subject = git(root, "show", "-s", "--format=%s", commit)
        match = re.fullmatch(r"(WMS-\d+): контракт тестов", subject)
        if not match:
            continue
        frozen = sorted(
            path for path in commit_changed_paths(root, commit)
            if not path.startswith("docs/requirements/")
        )
        if not frozen:
            continue
        task_id = match[1]
        contracts.append((commit, task_id, frozen))
    for commit, task_id, frozen in contracts:
        baselines, correction_errors = reviewed_contract_correction(
            root, task_id, commit
        )
        errors.extend(correction_errors)
        if correction_errors:
            continue
        overlap = set()
        corrected = set().union(*baselines.values())
        untouched = sorted(set(frozen) - corrected)
        if untouched:
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", commit, "HEAD", "--", *untouched)
                .splitlines()
            )
        for correction, paths in baselines.items():
            overlap.update(
                git(root, "diff", "--no-renames", "--name-only", correction, "HEAD", "--", *sorted(paths))
                .splitlines()
            )
        overlap = sorted(overlap)
        if overlap:
            errors.append(
                f"изменён контракт тестов {task_id} после его фиксации: "
                + ", ".join(overlap)
            )
    return errors


def check(root: Path, base: str) -> list[str]:
    errors = []
    if not all((root / name).is_file() for name in ("AGENTS.md", "CLAUDE.md")) or (root / "AGENTS.md").read_bytes() != (root / "CLAUDE.md").read_bytes():
        errors.append("AGENTS.md и CLAUDE.md должны существовать и содержать одинаковые правила.")
    for ref in task_refs(root, base):
        path = root / "docs" / "requirements" / f"{ref}.md"
        if not path.is_file():
            errors.append(f"{ref}: нет документа {path.relative_to(root)}.")
        else:
            errors.extend(
                f"{ref}: {error}"
                for error in document_errors(path.read_text(encoding="utf-8"), root)
            )
    errors.extend(contract_change_errors(root, base))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?", default="origin/etalon")
    args = parser.parse_args()
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel"))
    errors = check(root, args.base)
    if errors:
        print("\n".join(errors))
        return 1
    print("Документы задач заполнены; AGENTS.md и CLAUDE.md совпадают.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
