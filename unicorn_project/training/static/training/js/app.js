document.addEventListener('change', async (e)=>{
if(e.target && e.target.name==='business'){
  const business=e.target.value; const locSelect=document.querySelector('select[name="training_location"]'); if(!locSelect) return;
  locSelect.innerHTML='<option>Loading...</option>';
  const res=await fetch(`/api/locations/?business=${business}`); const data=await res.json();
  locSelect.innerHTML=''; (data.data||[]).forEach(item=>{ const o=document.createElement('option'); o.value=item.id; o.textContent=item.name; locSelect.appendChild(o); });
}});
