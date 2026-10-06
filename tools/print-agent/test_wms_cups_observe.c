// Read-only observer fixture. No connection or job submission reaches CUPS.
#include <cups/cups.h>
#include <cups/ipp.h>
#include <stdlib.h>
#include <string.h>
static int fixture_count=1,fixture_state=5;
static const char *fixture_title="WMS-title";
static http_t *fixture_connect(const char *host,int port,http_addrlist_t *addrlist,int family,http_encryption_t encryption,int blocking,int timeout,int *cancel) {
    return (http_t *)1;
}
static int fixture_jobs(http_t *http,cups_job_t **jobs,const char *name,int myjobs,int whichjobs) {
    static cups_job_t values[2];
    for(int i=0;i<2;i++) {
        memset(&values[i],0,sizeof(values[i]));
        values[i].id=41+i;values[i].dest="test-printer";values[i].title=(char *)fixture_title;values[i].state=fixture_state;
    }
    *jobs=values;return fixture_count;
}
static ipp_t *fixture_request(http_t *http,ipp_t *request,const char *resource) {
    ipp_op_t op=ippGetOperation(request);ippDelete(request);
    ipp_t *result=ippNew();ippSetStatusCode(result,IPP_STATUS_OK);
    if(op==IPP_OP_GET_JOB_ATTRIBUTES) {
        ippAddString(result,IPP_TAG_JOB,IPP_TAG_KEYWORD,"job-state-reasons",NULL,"queued-in-device");
        ippAddString(result,IPP_TAG_JOB,IPP_TAG_TEXT,"job-state-message",NULL,"Device said \"waiting\"\nPaper out");
    } else {
        ippAddInteger(result,IPP_TAG_PRINTER,IPP_TAG_ENUM,"printer-state",5);
        ippAddString(result,IPP_TAG_PRINTER,IPP_TAG_KEYWORD,"printer-state-reasons",NULL,"media-empty");
    }
    return result;
}
static void fixture_free(int count,cups_job_t *jobs) {}
static void fixture_close(http_t *http) {}
#define httpConnect2 fixture_connect
#define cupsGetJobs2 fixture_jobs
#define cupsDoRequest fixture_request
#define cupsFreeJobs fixture_free
#define httpClose fixture_close
#include "wms_cups_observe.c"
int main(int argc,char **argv) {
    if(argc>1) fixture_count=atoi(argv[1]);
    if(argc>2) fixture_state=atoi(argv[2]);
    if(argc>3) fixture_title=argv[3];
    return wms_cups_observe("test-printer",argc>4?argv[4]:"","WMS-title");
}
