const API = "/api";
export async function request(path, options={}) { const token = localStorage.getItem("cinema_token"); const auth = token ? {Authorization:`Bearer ${token}`} : {}; const res = await fetch(API + path, {headers:{"Content-Type":"application/json", ...auth, ...(options.headers||{})}, ...options}); const data = await res.json().catch(()=>({})); if(!res.ok) throw new Error(data.detail || `请求失败 ${res.status}`); return data; }
export const api = {
  login: (body)=>request("/auth/login", {method:"POST", body:JSON.stringify(body)}),
  plans:()=>request("/plans"),
  units:(id)=>request(`/plans/${id}/units`),
  observations:(id)=>request(`/plans/${id}/observations`),
  reviews:(id)=>request(`/plans/${id}/reviews`),
  summary:()=>request("/observations/summary"),
  createPlan:(body)=>request("/plans", {method:"POST",body:JSON.stringify(body)}),
  createUnit:(id,body)=>request(`/plans/${id}/units`, {method:"POST",body:JSON.stringify(body)}),
  start:(id)=>request(`/plans/${id}/start`, {method:"POST"}),
  addObservation:(id,body)=>request(`/plans/${id}/observations`, {method:"POST",body:JSON.stringify(body)}),
  analysis:(id,stratified=false)=>request(`/plans/${id}/analysis?stratified=${stratified}`, {method:"POST"}),
  approve:(id,rid,notes)=>request(`/plans/${id}/reviews/${rid}/approve`, {method:"POST",body:JSON.stringify({notes})}),
  hallChanges:(id)=>request(`/plans/${id}/hall-changes`),
  hallSegments:(id)=>request(`/plans/${id}/hall-changes/segments`),
  requestHallChange:(id,body)=>request(`/plans/${id}/hall-changes`, {method:"POST",body:JSON.stringify(body)}),
  retryHallChange:(id,attemptId,body)=>request(`/plans/${id}/hall-changes/${attemptId}/retry`, {method:"POST",body:JSON.stringify(body)}),
};
