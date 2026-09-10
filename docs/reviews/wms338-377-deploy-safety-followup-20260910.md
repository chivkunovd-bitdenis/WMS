# WMS-338 / WMS-377 — порядок миграций и закрытие старого порта

Общий deploy скрипт теперь останавливает api/worker/beat после сборки, до
миграции, делает частный pg_dump -Fc (каталог0700, файл0600), проверяет
pg_restore --list и только затем запускает миграции. Ошибка backup не
запускает миграцию; writers остаются остановленными. Это защита перед удалением
устаревшего stock ledger0261, не повод применять этот DDL в срочном mobile релизе.

После запуска web проверяется существующий seller маршрут через приватный
bridge172.18.0.1:8088, затем останавливается только старый web_seller того же
Compose project, установленного по метке контейнера БД. Чужие сервисы не
затрагиваются. CI smoke проверяет публичный HTTPS. SSH bootstrap берёт скрипт
из текущего origin/etalon, сохраняя его проверку SHA принадлежности etalon.

Три целевых теста проверяют фактический запуск shell со stub Git/Docker/Curl:
порядок stop → backup → verify → migration → route → legacy stop, права
backup, ошибку dump и испорченный архив. 3 PASS; bash -n, Ruff и Mypy PASS
в общем локальном scoped проходе. Production не изменён; живой backup, миграция,
закрытие порта и независимое review этого delta ещё не выполнены.


После independent review27228 исправленыstdin и потеряexitstatus: workflow
получаетскрипт checkedassignment ивыполняет bash-c </dev/null; pg_dumpтакже
безstdin; dockerpsдляlegacycheckedassignment, пустойсписокуспешен.
7целевыхtestsPASS: dump/archivefail, listingfail,emptylist, actualworkflow
bootstrap gitshowfail и scriptcommandчитающаяstdin. Ruff/bash-nPASS.
Повторноеindependentreviewэтогопоследнегоdeltaещёнепройдено.


## WMS-270/377: topology preflight before deployment

Independent review at891281e7 acceptedauth/limiter butfoundoneP2: hardcodedtrustsubnetswerenotcomparedwithactualDockerbridgesbeforedeployment. Newverify-wms-host-network.py reads onlynetworkmetadata andComposeprojectlabel; validatescandidateoverlay/Caddytrust, existingWMSdefaultsubnet/gateway, actualapi/webmembership andHTTPSedgegateway/subnet. Drift/missingorambiguousnetwork/containerfailsbeforebuild,writershutdownorDDL; nothingrecreatesnetworks. NormalcontainerIPchangeinsidepreservedsubnetpasses.

15focusedtestsPASS18.67s coveroldbackup/bootstrap/legacybehavior, actualdeployscriptfailurebeforebuildonnetworkdrift, WMS/edgechangedsubnets, detachedapi, missingnetwork, twoedges, within-subnetcontainerreplacement. ScopedRuff/bash-nPASSafterformatting/executablemodefix. Rootranthesameverifieragainstactualservermetadatawithcandidatepublicconfigsinephemeraltempdir: verifiedtrue, WMS172.21.0.0/16, edge172.18.0.0/16. ActiveHTTPSedgeiswb-finance-caddy-1; existingweb172.21.0.6, edge172.18.0.9. Noactualconfig/network/servicechange. ExactproofJSONresumed/wms377-candidate-network-preflight-20260910.json. FullHTTPSclientchain/closedportsremainafterdeploychecks.


## Retry after a failed backup

Independent review of10aeccb3 found a recovery regression: running-onlyAPIlookup would reject a retry after the existing backup failure path deliberately stopped API. Fixed: include stoppedexistingDB/API/web; require the same saved networkID and configuredNetworkMode for stoppedservices, without demanding an activeIP. Runningservices retain subnet/gateway/IP checks. No oldAPI is started merely to pass preflight. Edge still must be a single running HTTPS listener.

18 scoped tests PASS10.34s, Ruff andbashsyntaxPASS. New sequentialtest executes the real deploy script against a statefulDockerstub: firstbackupfailsandAPIremainsstopped; seconddeploymentusesits savedattachmentwithblankIP, completesbackupandmigration beforeapplicationstart. WrongconfigurednetworkforstoppedAPI remainsrejected. Realserverreadonlyinspect confirms currentAPINetworkModewms_prod_default/runningtrue. Originaltopologyreceipt remains evidencefor10aeccb3; newstoppedrecovery is synthetic, notanactualproductionstop.
