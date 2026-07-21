import test from "node:test";
import { accessAdvice, renderCard } from "../static/js/cards.js";
import assert from "node:assert/strict";
import { getVisibleKeys, selectCurrentResults, selectionSummary, taskProgress, restartCandidates, isLatestResponse, moveKey, canReorder, keysFingerprint } from "../static/js/state.js";
const keys=[{id:1,status:"up",name:"Alpha",models:["gpt-4"]},{id:2,status:"down",name:"Beta",models:[]}];
test("visible filtering",()=>assert.deepEqual(getVisibleKeys(keys,"up","").map(k=>k.id),[1]));
test("select current only",()=>assert.deepEqual([...selectCurrentResults(new Set(),[keys[0]],true)],[1]));
test("selection summary includes hidden",()=>assert.deepEqual(selectionSummary(new Set([1,2]),[keys[0]]),{total:2,visible:1,hidden:1,resultTotal:1}));
test("task progress",()=>assert.deepEqual(taskProgress({total:4,completed:2,status:"running"}),{percent:50,label:"2/4",terminal:false}));
test("restart rollback URL first",()=>assert.deepEqual(restartCandidates({status:"rolled_back",old_url:"old",target_url:"new"}),["old","new"]));
test("stale response",()=>assert.equal(isLatestResponse(1,2),false));
test("move key before target",()=>assert.deepEqual(moveKey(keys,2,1).map(k=>k.id),[2,1]));
test("reorder only all unfiltered",()=>assert.equal(canReorder("all",""),true));
test("reorder disabled while filtered",()=>assert.equal(canReorder("up",""),false));
const issueKeys=[{id:1,status:"rate_limited",name:"R"},{id:2,status:"degraded",name:"D"},{id:3,status:"up",name:"U"}];
test("issue filtering",()=>assert.deepEqual(getVisibleKeys(issueKeys,"issue","").map(k=>k.id),[1,2]));
test("rate limit filtering uses overall status",()=>assert.deepEqual(getVisibleKeys(issueKeys,"rate_limited","").map(k=>k.id),[1]));
test("fingerprint changes with status",()=>{
  const a=keysFingerprint([{id:1,status:"up",latency_ms:1}]);
  const b=keysFingerprint([{id:1,status:"down",latency_ms:1}]);
  assert.notEqual(a,b);
});
test("fingerprint changes with model_last_error",()=>{
  const a=keysFingerprint([{id:1,status:"up",model_status:"up",model_last_error:""}]);
  const b=keysFingerprint([{id:1,status:"up",model_status:"up",model_last_error:"stale"}]);
  assert.notEqual(a,b);
});
test("fingerprint changes with model_probe_adapter",()=>{
  const a=keysFingerprint([{id:1,status:"up",model_status:"up",model_probe_adapter:"openai_chat"}]);
  const b=keysFingerprint([{id:1,status:"up",model_status:"up",model_probe_adapter:"openai_responses"}]);
  assert.notEqual(a,b);
});
const problemKeys=[{id:1,status:"up",name:"U"},{id:2,status:"down",name:"D"},{id:3,status:"auth_error",name:"A"},{id:4,status:"unknown",name:"N"},{id:5,status:"rate_limited",name:"R"}];
test("problem filtering",()=>assert.deepEqual(getVisibleKeys(problemKeys,"problem","").map(k=>k.id),[2,3,4,5]));

const cardState={checking:new Set(),selected:new Set(),status:"all",query:""};
test("card shows each protocol's individual status",()=>{
  const html=renderCard({id:1,status:"up",name:"Mixed",base_url:"https://example.com",openai_status:"up",anthropic_status:"rate_limited"},cardState);
  assert.match(html,/OpenAI · 在线/);
  assert.doesNotMatch(html,/Anthropic/);
});
test("card hides stale protocol flags after failure",()=>{
  const html=renderCard({id:1,status:"down",name:"Failed",base_url:"https://example.com",supports_openai:true,supports_anthropic:true},cardState);
  assert.match(html,/未确认/);
  assert.doesNotMatch(html,/OpenAI/);
  assert.doesNotMatch(html,/Anthropic/);
});
test("card distinguishes strict model verification from protocol availability",()=>{
  const unverified=renderCard({id:1,status:"up",name:"Key",base_url:"https://example.com",check_model:"gpt-test",model_status:"up",model_verification_version:0},cardState);
  const verified=renderCard({id:1,status:"up",name:"Key",base_url:"https://example.com",check_model:"gpt-test",model_status:"up",model_last_check_at:1,model_verification_version:1},cardState);
  assert.match(unverified,/未严格验证/);
  assert.match(verified,/严格验证/);
  assert.doesNotMatch(verified,/未严格验证/);
});
test("card shows direct ccswitch advice for chat adapter",()=>{
  const html=renderCard({id:1,status:"up",name:"Key",base_url:"https://example.com",check_model:"gpt-test",model_status:"up",model_verification_version:1,model_probe_adapter:"openai_chat"},cardState);
  assert.match(html,/可直接接入 ccswitch/);
  assert.match(html,/OpenAI chat\/completions 可用/);
});
test("card shows wrapper advice for responses-only adapter",()=>{
  const html=renderCard({id:1,status:"up",name:"Key",base_url:"https://example.com",check_model:"gpt-test",model_status:"up",model_verification_version:1,model_probe_adapter:"openai_responses"},cardState);
  assert.match(html,/需 Responses 兼容壳/);
  assert.match(html,/仅 \/responses 严格验证通过/);
});
test("access advice treats strict model rate limit as not directly usable",()=>{
  assert.deepEqual(accessAdvice({status:"rate_limited",check_model:"gpt",model_status:"rate_limited",model_verification_version:1}),{
    tone:"rate-limited",label:"暂缓接入：严格验证限流",detail:"等待额度恢复后再用于 ccswitch"
  });
});
