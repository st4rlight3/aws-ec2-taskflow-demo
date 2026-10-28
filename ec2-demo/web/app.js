const $ = id => document.getElementById(id);
const names = {todo:'Chưa bắt đầu',doing:'Đang thực hiện',done:'Đã hoàn thành'};
let tasks = [], pendingDelete = null, toastTimer, searchTimer, loadSequence = 0;
async function api(path,method='GET',data){
 const options={method,headers:{'X-TaskFlow-Request':'1'}};
 if(data!==undefined){options.headers['Content-Type']='application/json';options.body=JSON.stringify(data);}
 const response=await fetch(path,options);let result;
 try{result=await response.json();}catch{throw new Error('Máy chủ trả về dữ liệu không hợp lệ');}
 if(!response.ok){if(response.status===401&&path!=='/api/login')showLogin();throw new Error(result.error||'Yêu cầu chưa thành công');}
 return result;
}
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function showLogin(){clearTimeout(searchTimer);loadSequence++;$('login-screen').hidden=false;$('app-screen').hidden=true;}
function showApp(mode){$('login-screen').hidden=true;$('app-screen').hidden=false;$('environment').textContent=mode==='local'?'Môi trường cục bộ':'Cấu hình triển khai EC2';}
function query(){return new URLSearchParams({q:$('search').value,status:$('status-filter').value,priority:$('priority-filter').value});}
function el(tag,text,className){const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;}
async function load(){
 const sequence=++loadSequence;const result=await api('/api/tasks?'+query());if(sequence!==loadSequence)return;
 tasks=result.tasks;const s=result.summary,total=s.todo+s.doing+s.done;
 $('total-count').textContent=total;for(const key of Object.keys(names))$(key+'-count').textContent=s[key];
 $('completion-rate').textContent=(total?Math.round(s.done/total*100):0)+'% tổng công việc';
 $('visible-count').textContent=tasks.length;$('result-count').textContent=`Hiển thị ${tasks.length} / ${total} công việc`;
 const body=$('task-list');body.replaceChildren();$('empty').hidden=tasks.length>0;
 for(const task of tasks){
  const row=el('tr');const title=el('td',task.title);title.append(el('span','TF-'+String(task.id).padStart(3,'0'),'task-ref'));row.append(title);
  const owner=el('td'),ownerWrap=el('span',undefined,'owner');ownerWrap.append(el('span',task.owner.slice(0,1).toUpperCase(),'owner-letter'),el('span',task.owner));owner.append(ownerWrap);row.append(owner);
  const priority=el('td');priority.append(el('span',{high:'Cao',medium:'Vừa',low:'Thấp'}[task.priority],'priority '+task.priority));row.append(priority);
  const status=el('td'),select=el('select',undefined,'status-select '+task.status);select.setAttribute('aria-label','Trạng thái của '+task.title);
  for(const [key,label] of Object.entries(names)){const option=el('option',label);option.value=key;option.selected=key===task.status;select.append(option);}
  select.addEventListener('change',async()=>{select.disabled=true;try{await api('/api/tasks/'+task.id,'PATCH',{status:select.value});await load();toast('Đã cập nhật trạng thái');}catch(error){select.value=task.status;toast(error.message);}finally{select.disabled=false;}});status.append(select);row.append(status);
  const [year,month,day]=task.due.split('-');row.append(el('td',`${day}/${month}/${year}`));
  const actions=el('td');const edit=el('button','Sửa','text-button');edit.setAttribute('aria-label','Sửa '+task.title);edit.addEventListener('click',()=>openEditor(task));
  const remove=el('button','Xóa','text-button delete-button');remove.setAttribute('aria-label','Xóa '+task.title);remove.addEventListener('click',()=>{pendingDelete=task.id;$('delete-description').textContent='Bạn muốn xóa “'+task.title+'”?';$('delete-dialog').showModal();});actions.append(edit,remove);row.append(actions);body.append(row);
 }
}
function openEditor(task){$('task-form').reset();$('form-error').textContent='';$('task-id').value=task?.id||'';$('dialog-title').textContent=task?'Chỉnh sửa công việc':'Thêm công việc';for(const field of ['title','owner','priority','status','due']){if(task)$('task-'+field).value=task[field];}if(!task){const now=new Date();now.setDate(now.getDate()+3);$('task-due').value=[now.getFullYear(),String(now.getMonth()+1).padStart(2,'0'),String(now.getDate()).padStart(2,'0')].join('-');}$('task-dialog').showModal();$('task-title').focus();}
$('login-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;$('login-error').textContent='';try{await api('/api/login','POST',{password:$('password').value});const session=await api('/api/session');showApp(session.mode);await load();$('password').value='';}catch(error){$('login-error').textContent=error.message;}finally{button.disabled=false;}});
$('logout').addEventListener('click',async()=>{try{await api('/api/logout','POST',{});showLogin();}catch(error){toast(error.message);}});
$('add-task').addEventListener('click',()=>openEditor());
for(const id of ['close-dialog','cancel-dialog'])$(id).addEventListener('click',()=>$('task-dialog').close());
$('task-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.submitter;button.disabled=true;const body={};for(const field of ['title','owner','priority','status','due'])body[field]=$('task-'+field).value;const id=$('task-id').value;try{await api(id?'/api/tasks/'+id:'/api/tasks',id?'PATCH':'POST',body);$('task-dialog').close();await load();toast(id?'Đã lưu thay đổi':'Đã thêm công việc');}catch(error){$('form-error').textContent=error.message;}finally{button.disabled=false;}});
$('cancel-delete').addEventListener('click',()=>$('delete-dialog').close());
$('confirm-delete').addEventListener('click',async()=>{const button=$('confirm-delete');button.disabled=true;try{await api('/api/tasks/'+pendingDelete,'DELETE');$('delete-dialog').close();await load();toast('Đã xóa công việc');}catch(error){toast(error.message);}finally{button.disabled=false;}});
$('search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>load().catch(error=>{if(!$('app-screen').hidden)toast(error.message);}),220);});
for(const id of ['status-filter','priority-filter'])$(id).addEventListener('change',()=>load().catch(error=>{if(!$('app-screen').hidden)toast(error.message);}));
$('export').addEventListener('click',()=>{window.location.href='/api/export?'+query();});
function showView(which){$('board-view').hidden=which!=='board';$('architecture-view').hidden=which!=='architecture';$('board-nav').classList.toggle('active',which==='board');$('architecture-nav').classList.toggle('active',which==='architecture');}
$('board-nav').addEventListener('click',()=>showView('board'));$('architecture-nav').addEventListener('click',()=>showView('architecture'));$('back-to-board').addEventListener('click',()=>showView('board'));
(async()=>{try{const session=await api('/api/session');if(session.mode!=='local')$('password-hint').textContent='Dùng mã truy cập đã đặt khi cài máy chủ.';if(session.authenticated){showApp(session.mode);await load();}}catch(error){$('login-error').textContent='Chưa kết nối được máy chủ. '+error.message;}})();
