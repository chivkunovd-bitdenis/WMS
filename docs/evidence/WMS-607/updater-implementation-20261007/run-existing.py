"""Stdlib JUnit writer for the actual additive unittest module; no implementation."""
import argparse
import importlib.util
from pathlib import Path
import sys
import time
import unittest
import xml.etree.ElementTree as ET

parser=argparse.ArgumentParser();parser.add_argument('--report',required=True);parser.add_argument('cases',nargs='*');args=parser.parse_args()
root=Path(__file__).resolve().parents[4]
modules=[]
for name in ('test_macos_artmaks_contract','test_macos_default_printer','test_macos_native','test_macos_artmaks_http_contract'):
    spec=importlib.util.spec_from_file_location(name,root/'tools/print-agent'/ (name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    modules.append(module)
rows={}
class Result(unittest.TextTestResult):
    def startTest(self,test):
        super().startTest(test);rows[test.id()]={'start':time.monotonic(),'failure':[],'error':[],'skip':None}
    def addFailure(self,test,err):
        super().addFailure(test,err);rows[test.id()]['failure'].append(self._exc_info_to_string(err,test))
    def addError(self,test,err):
        super().addError(test,err)
        if test.id() not in rows:rows[test.id()]={'start':time.monotonic(),'failure':[],'error':[],'skip':None}
        rows[test.id()]['error'].append(self._exc_info_to_string(err,test))
    def addSkip(self,test,reason):
        super().addSkip(test,reason);rows[test.id()]['skip']=reason
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err:rows[test.id()]['failure' if issubclass(err[0],test.failureException) else 'error'].append(str(subtest)+': '+self._exc_info_to_string(err,test))
    def stopTest(self,test):
        rows[test.id()]['elapsed']=time.monotonic()-rows[test.id()]['start'];super().stopTest(test)
suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(module) for module in modules)
r=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
xml=ET.Element('testsuite',name='WMS607.existingMacContracts',tests=str(len(rows)),failures=str(sum(bool(x['failure']) for x in rows.values())),errors=str(sum(bool(x['error']) for x in rows.values())),skipped=str(sum(x['skip'] is not None for x in rows.values())))
for identifier,row in rows.items():
    classname,name=identifier.rsplit('.',1);case=ET.SubElement(xml,'testcase',classname=classname,name=name,time=str(row.get('elapsed',0)))
    for kind in ('failure','error'):
        if row[kind]:ET.SubElement(case,kind).text='\n'.join(row[kind])
    if row['skip'] is not None:ET.SubElement(case,'skipped',message=row['skip'])
out=Path(args.report);out.parent.mkdir(parents=True,exist_ok=True);ET.ElementTree(xml).write(out,encoding='utf-8',xml_declaration=True)
sys.exit(0 if r.wasSuccessful() else 1)
