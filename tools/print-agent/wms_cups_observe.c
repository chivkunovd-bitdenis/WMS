// Read-only CUPS observer, run in a bounded subprocess by the Swift runtime.
#include <cups/cups.h>
#include <cups/ipp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void string(const char *s) {
    putchar('"');
    for (const unsigned char *p=(const unsigned char *)(s ? s : ""); *p; p++) {
        if (*p=='"' || *p=='\\') { putchar('\\'); putchar(*p); }
        else if (*p<32) printf("\\u%04x", *p);
        else putchar(*p);
    }
    putchar('"');
}
static void values(ipp_t *r, const char *name) {
    ipp_attribute_t *a=ippFindAttribute(r,name,IPP_TAG_ZERO);
    putchar('[');
    if(a) for(int i=0;i<ippGetCount(a);i++) {
        if(i) putchar(','); string(ippGetString(a,i,NULL));
    }
    putchar(']');
}
static ipp_t *request(http_t *h, ipp_op_t operation, const char *uri, const char *resource) {
    ipp_t *r=ippNewRequest(operation);
    ippAddString(r,IPP_TAG_OPERATION,IPP_TAG_URI,"printer-uri",NULL,uri);
    ippAddString(r,IPP_TAG_OPERATION,IPP_TAG_NAME,"requesting-user-name",NULL,cupsUser());
    return cupsDoRequest(h,r,resource);
}
int wms_cups_observe(const char *queue, const char *receipt, const char *title) {
    http_t *h=httpConnect2(cupsServer(),ippPort(),NULL,AF_UNSPEC,HTTP_ENCRYPTION_IF_REQUESTED,1,3000,NULL);
    if(!h) { printf("{\"error\":\"CUPS connection unavailable\"}\n"); return 0; }
    cups_job_t *jobs=NULL;
    int count=cupsGetJobs2(h,&jobs,queue,1,CUPS_WHICHJOBS_ALL);
    if(count<0) {
        printf("{\"error\":"); string(cupsLastErrorString()); printf("}\n"); httpClose(h); return 0;
    }
    int wanted=0;
    if(receipt && *receipt) { const char *dash=strrchr(receipt,'-'); if(dash) wanted=atoi(dash+1); }
    int matches=0, found=-1;
    for(int i=0;i<count;i++) {
        if(strcmp(jobs[i].dest,queue)) continue;
        if(wanted ? jobs[i].id!=wanted : !title || strcmp(jobs[i].title,title)) continue;
        if(wanted && title && *title && strcmp(jobs[i].title,title)) continue;
        matches++; found=i;
    }
    printf("{\"matches\":%d",matches);
    if(matches==1) {
        cups_job_t j=jobs[found];
        printf(",\"receipt\":"); char receiptOut[1024]; snprintf(receiptOut,sizeof(receiptOut),"%s-%d",queue,j.id); string(receiptOut);
        printf(",\"jobState\":%d,\"jobTitle\":",j.state); string(j.title);
        char uri[1024]; snprintf(uri,sizeof(uri),"ipp://localhost/jobs/%d",j.id);
        ipp_t *r=ippNewRequest(IPP_OP_GET_JOB_ATTRIBUTES);
        ippAddString(r,IPP_TAG_OPERATION,IPP_TAG_URI,"job-uri",NULL,uri);
        ippAddString(r,IPP_TAG_OPERATION,IPP_TAG_NAME,"requesting-user-name",NULL,cupsUser());
        ipp_t *response=cupsDoRequest(h,r,"/");
        if(response && ippGetStatusCode(response)<IPP_STATUS_ERROR_BAD_REQUEST) {
            printf(",\"jobStateReasons\":"); values(response,"job-state-reasons");
            printf(",\"jobStateMessage\":"); ipp_attribute_t *a=ippFindAttribute(response,"job-state-message",IPP_TAG_TEXT); string(a?ippGetString(a,0,NULL):"");
        }
        if(response) ippDelete(response);
    }
    char uri[1024], resource[1024];
    snprintf(resource,sizeof(resource),"/printers/%s",queue);
    httpAssembleURI(HTTP_URI_CODING_ALL,uri,sizeof(uri),"ipp",NULL,"localhost",631,resource);
    ipp_t *response=request(h,IPP_OP_GET_PRINTER_ATTRIBUTES,uri,resource);
    if(response && ippGetStatusCode(response)<IPP_STATUS_ERROR_BAD_REQUEST) {
        ipp_attribute_t *a=ippFindAttribute(response,"printer-state",IPP_TAG_ENUM);
        if(a) printf(",\"printerState\":%d",ippGetInteger(a,0));
        printf(",\"printerStateReasons\":"); values(response,"printer-state-reasons");
        printf(",\"printerStateMessage\":"); a=ippFindAttribute(response,"printer-state-message",IPP_TAG_TEXT); string(a?ippGetString(a,0,NULL):"");
    }
    if(response) ippDelete(response);
    printf("}\n"); cupsFreeJobs(count,jobs); httpClose(h); return 0;
}
