# Picking test-source synchronization

Product P: `7dbce79566246f7467bf1b7c84efa8cbe8f1cd9b`.
Original independent browser contract: `378b481cdc218bd6385140ea19202d2a25b4b94e`.

The c3 run 37674200067 passed 29 base and 39 extended cases. `print-picked`
observed an existing popup with `headers=[]` before asynchronous preparation
finished. Its DB checkpoint verified one pick; browser errors were empty and
print-assets returned 200. Opening the window is deliberately synchronous;
writing the final document follows sticker, pick-options and picking-context reads.

The only browser contract change is a bounded Playwright assertion that twelve
header cells exist before reading their text. The exact header array, all row,
source, origin and stock readback assertions remain unchanged; no case is removed.
Independent parent review of this change was supplied before publication.

`popup-race.log` records two real component tests (single supply and assembly):
hold the pick-options response, assert one opened popup and no final document,
release the response, assert twelve headers and the original exact color cells.
Both passed. This reproduces the invalidity of treating popup creation as print
readiness; it does not substitute for the full real-stack 69-case rerun.
