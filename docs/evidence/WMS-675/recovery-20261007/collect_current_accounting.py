"""Read existing exact-scope SQL through the installed tenant-only gateway. No roles/writes."""
from pathlib import Path
import argparse,csv,hashlib,io,json,sys
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[4]
SOURCE=ROOT/'docs/reviews/wms675-evidence-20261006/accounting-refresh-20261006-attempt1'
TENANT='b80a893b-ab87-42b6-8fd7-6d41502c900f'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
 sys.path.insert(0,str(ROOT/'tools/support_agent'))
 from support_agent.config import load_config
 from support_agent.prod_sql import ProdSqlSettings,role_for_tenant,run_query
 cfg=load_config('/Users/deniscivkunov/.wms-support-agent/config.json').prod_db
 settings=ProdSqlSettings(ssh_host=cfg.ssh_host,ssh_user=cfg.ssh_user,ssh_key_path=cfg.ssh_key_path,known_hosts=cfg.known_hosts,row_limit=200,timeout_sec=30,max_bytes=200000,db_role=role_for_tenant(TENANT))
 names=('identity','orders_positions_reserves','ledger','unlinked_fbs_movements','balances_vs_all_movements','balances_locations','billing_entries','operation_facts','supply_operations','other_negative_since_audit','new_history_attribution')
 manifest={'tenant_id':TENANT,'role':settings.db_role,'writes':0,'external_calls':0,'started_at':datetime.now(timezone.utc).isoformat(),'queries':[],'snapshot_consistency':'Separate read-only gateway SELECTs; actual native locks recheck before any conduct.'}
 for name in names:
  query=(SOURCE/(name+'.sql')).read_text();entry={'name':name,'sql_sha256':hashlib.sha256(query.encode()).hexdigest()}
  (args.output/(name+'.sql')).write_text(query)
  try:
   result=run_query(settings,query)
   if '# вывод обрезан' in result:raise ValueError('truncated')
   rows=list(csv.DictReader(io.StringIO(result)));(args.output/(name+'.csv')).write_text(result);entry.update(status='ok',rows=len(rows),sha256=hashlib.sha256(result.encode()).hexdigest())
  except Exception as exc:entry.update(status='failed',error_type=type(exc).__name__)
  manifest['queries'].append(entry);(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(entry),flush=True)
 manifest['finished_at']=datetime.now(timezone.utc).isoformat();(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return 0 if all(q['status']=='ok' for q in manifest['queries']) else 2
if __name__=='__main__':raise SystemExit(main())
