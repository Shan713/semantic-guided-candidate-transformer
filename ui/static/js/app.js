/**
 * SGCT Dashboard — Client-Side Behaviour
 * Vanilla JS, zero framework dependency.
 */
(function(){
'use strict';

// ---------------------------------------------------------------------------
// Toast notification
// ---------------------------------------------------------------------------
window.showToast = function(msg,type){
    var c = document.getElementById('toast-container');
    if(!c){c=document.createElement('div');c.id='toast-container';document.body.appendChild(c);}
    var t = document.createElement('div');
    t.className = 'toast-msg' + (type==='error' ? ' err' : '');
    t.innerHTML = '<i class="bi ' + (type==='error'?'bi-x-circle-fill':'bi-check-circle-fill') + '"></i>' + msg;
    c.appendChild(t);
    setTimeout(function(){t.style.opacity='0';t.style.transition='opacity .3s';setTimeout(function(){t.remove()},300)},2400);
};

// ---------------------------------------------------------------------------
// Copy JSON from a <code> element
// ---------------------------------------------------------------------------
window.copyJson = function(id){
    var el = document.getElementById(id);
    if(!el) return;
    var text = el.textContent;
    if(navigator.clipboard && navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(function(){showToast('Copied','success')}).catch(function(){fb(text)});
    }else{fb(text);}
};
function fb(text){
    var ta = document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();
    try{document.execCommand('copy');showToast('Copied','success')}catch(e){showToast('Copy failed','error')}
    document.body.removeChild(ta);
}

// ---------------------------------------------------------------------------
// Upload zone file selection
// ---------------------------------------------------------------------------
window.handleFileSelect = function(input,zoneId,nameId){
    var z = document.getElementById(zoneId);
    var n = document.getElementById(nameId);
    if(input.files.length>0){z.classList.add('has-file');n.textContent=input.files[0].name}
    else{z.classList.remove('has-file');n.textContent=''}
};

// ---------------------------------------------------------------------------
// Reset upload form
// ---------------------------------------------------------------------------
window.resetForm = function(){
    document.querySelectorAll('.upload-zone').forEach(function(z){z.classList.remove('has-file')});
    document.querySelectorAll('.fname').forEach(function(e){e.textContent=''});
};

})();
