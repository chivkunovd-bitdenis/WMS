# WMS-401 — technical order QR in box assignment

The saved screen `outputs/wms401-android-20260909/71-realqr-box-result.png` was opened and shows the failure “Нет нераспределённого заказа с таким кодом”. The mobile sticker DTO contains only the printed code and status; the local box scan therefore cannot match the technical WB label payload.

Mobile commit `3b198e7c81ca13f7980c45565170fc25ba9e6bbf`, based on `e2d43b5cc7817bf5be164b53ef9e2ef723c4f718`, keeps the existing local box and order matching. On an order-match miss it calls the already available supply-scoped `lookupKiz` GET, then accepts the returned ID only if it belongs to an unassigned order in the current workspace. Assignment still uses the existing `assignOrders` call. The marking-only `canBind` and `needsConfirmation` flags are not used as box gates. No backend API, schema, web frontend, stock operation or navigation change was made.

The deployed backend source `c3aa4dfaccbc99c6d58cf9e5a864bc248cc8ae3f` was inspected using Git. The lookup searches the technical sticker barcode before the printed code and product barcode, scoped by tenant and supply. It accepts active marking-write statuses (`new`, `in_supply`, `assembling`, `packed`) and rejects other statuses with HTTP 409 `order_frozen`. That pre-existing lookup limit remains; the change is not represented as a universal lookup for every order status.

Targeted `FbsViewModelTest` passed 16/16 tests, with no failures, errors or skips. Four new tests check the exact technical payload path, assignment of the returned order rather than the oldest different order, ignoring marking flags, retaining local printed-code matching without a GET, rejection of absent/already-assigned IDs and prevention of assignment after lookup HTTP 409. No marking validation or commit is called by the QR assignment test.

The mobile checkout is committed and clean. Only the safe patch and test proof are published here; complete mobile Git history is not published. No new APK was assembled: root requested one later batch build. The author did not operate the AVD. The actual corrected QR scan remains pending on that future APK.

Evidence: [safe patch](artifacts/wms401-box-qr-fix-20260909/mobile-box-qr-fix.patch), [test XML](artifacts/wms401-box-qr-fix-20260909/targeted-tests.xml), [proof](artifacts/wms401-box-qr-fix-20260909/proof.json).
