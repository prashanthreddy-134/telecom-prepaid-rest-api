import http from 'k6/http';
import { check } from 'k6';
export const options={scenarios:{ipl:{executor:'constant-arrival-rate',rate:200,timeUnit:'1s',duration:'60s',preAllocatedVUs:50,maxVUs:300}},thresholds:{http_req_duration:['p(95)<300'],http_req_failed:['rate<0.01']}};
export default function(){const r=http.get(`${__ENV.BASE_URL||'http://localhost:8000'}/api/v1/plans?page_num=1&size=20`);check(r,{'200 OK':x=>x.status===200});}
