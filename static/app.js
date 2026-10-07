/* 文件中转站 前端逻辑（桌面端 + 手机端共用） */
(function () {
  'use strict';

  var page = document.body.getAttribute('data-page') || 'desktop';
  var IS_MOBILE = page === 'mobile';
  var state = { files: [], sel: new Set(), info: null, uploading: 0 };
  var skew = 0;

  function $(id) { return document.getElementById(id); }
  function now() { return Date.now() / 1000 - skew; }
  function mk(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  /* ---------- 格式化 ---------- */
  function fmtSize(n) {
    n = Number(n) || 0;
    var u = ['B', 'KB', 'MB', 'GB', 'TB'], i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i === 0 ? Math.round(n) : n.toFixed(1)) + ' ' + u[i];
  }
  function fmtRemain(sec) {
    sec = Math.max(0, Math.floor(sec));
    var d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
    if (d >= 1) return '剩 ' + d + ' 天 ' + h + ' 小时';
    if (h >= 1) return '剩 ' + h + ' 小时 ' + m + ' 分';
    if (m >= 1) return '剩 ' + m + ' 分钟';
    return '即将过期';
  }
  function remainClass(sec) { return sec < 86400 ? 'soon' : (sec < 172800 ? 'warn' : ''); }
  function fmtAgo(sec) {
    sec = Math.max(0, Math.floor(sec));
    if (sec < 60) return '刚刚';
    if (sec < 3600) return Math.floor(sec / 60) + ' 分钟前';
    if (sec < 86400) return Math.floor(sec / 3600) + ' 小时前';
    return Math.floor(sec / 86400) + ' 天前';
  }
  function fmtTime(ts) {
    var d = new Date(ts * 1000), p = function (x) { return (x < 10 ? '0' : '') + x; };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  function extTag(name) {
    var m = /\.([A-Za-z0-9]{1,5})$/.exec(name || '');
    return m ? m[1].toUpperCase() : 'FILE';
  }

  var toastTimer = null;
  function toast(msg, isErr) {
    var t = $('toast');
    if (!t) return;
    t.textContent = msg;
    t.className = 'toast' + (isErr ? ' err' : '');
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { t.hidden = true; }, 2800);
  }

  function copyText(text) {
    var done = function () { toast('链接已复制：' + text); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallback(); });
    } else { fallback(); }
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch (e) { toast('复制失败，请手动选择链接', true); }
      document.body.removeChild(ta);
    }
  }

  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      return r.text().then(function (txt) {
        var data = {};
        try { data = JSON.parse(txt); } catch (e) { data = {}; }
        if (!r.ok) throw new Error(data.error || ('请求失败 HTTP ' + r.status));
        return data;
      });
    });
  }

  /* ---------- 状态栏 ---------- */
  function renderChips() {
    var box = $('chips');
    if (!box) return;
    var meta = state.meta || {};
    var items = [
      ['有效期', (meta.ttl_days || 7) + ' 天'],
      ['文件', (meta.count || 0) + ' 个'],
      ['已用', fmtSize(meta.total_size || 0)],
    ];
    if (state.info && state.info.disk_free) items.push(['服务器剩余', fmtSize(state.info.disk_free)]);
    box.textContent = '';
    items.forEach(function (pair) {
      var chip = mk('span', 'chip');
      chip.appendChild(document.createTextNode(pair[0] + ' '));
      chip.appendChild(mk('b', null, pair[1]));
      box.appendChild(chip);
    });
  }

  /* ---------- 列表渲染 ---------- */
  function absoluteUrl(id) { return location.origin + '/d/' + id; }

  function buildRow(f) {
    var t = now();
    var li = mk('li', 'frow' + (state.sel.has(f.id) ? ' sel' : ''));
    li.setAttribute('data-id', f.id);

    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = state.sel.has(f.id);
    cb.addEventListener('change', function () { toggle(f.id, cb.checked); });
    var cbl = mk('label', 'check');
    cbl.appendChild(cb);
    li.appendChild(cbl);

    var nameBox = mk('div', 'fname');
    var nm = mk('span', 'fname-text', f.name);
    nm.title = f.name;
    nameBox.appendChild(nm);
    nameBox.appendChild(mk('span', 'tag', extTag(f.name)));
    li.appendChild(nameBox);

    li.appendChild(mk('div', 'fsize', fmtSize(f.size)));

    var up = mk('div', 'fmeta', '上传于 ' + fmtAgo(t - f.uploaded_at));
    up.title = fmtTime(f.uploaded_at);
    li.appendChild(up);

    var remBox = mk('div');
    remBox.appendChild(mk('span', 'badge ' + remainClass(f.expires_at - t), fmtRemain(f.expires_at - t)));
    li.appendChild(remBox);

    var acts = mk('div', 'facts');
    var dl = mk('a', 'btn btn-ghost btn-sm', '下载');
    dl.href = '/d/' + f.id;
    dl.setAttribute('download', f.name);
    acts.appendChild(dl);
    if (!IS_MOBILE) {
      var cp = mk('button', 'btn btn-ghost btn-sm', '复制链接');
      cp.type = 'button';
      cp.addEventListener('click', function () { copyText(absoluteUrl(f.id)); });
      acts.appendChild(cp);
    }
    var del = mk('button', 'btn btn-ghost btn-sm btn-danger', '删除');
    del.type = 'button';
    del.addEventListener('click', function () { removeIds([f.id]); });
    acts.appendChild(del);
    li.appendChild(acts);

    return li;
  }

  function renderList() {
    var list = $('filelist');
    if (!list) return;
    list.textContent = '';
    state.files.forEach(function (f) { list.appendChild(buildRow(f)); });

    var empty = $('empty');
    if (empty) empty.hidden = state.files.length > 0;

    var summary = $('listSummary');
    var meta = state.meta || {};
    if (summary) {
      summary.textContent = state.files.length
        ? '共 ' + state.files.length + ' 个文件 · ' + fmtSize(meta.total_size || 0) + ' · 上传后保留 ' + (meta.ttl_days || 7) + ' 天'
        : '上传的文件保留 ' + (meta.ttl_days || 7) + ' 天，到期自动删除';
    }
    updateSelUI();
  }

  function renderAll() { renderList(); renderChips(); }

  function updateSelUI() {
    var all = $('selectAll');
    if (all) {
      all.checked = state.files.length > 0 && state.sel.size === state.files.length;
      all.indeterminate = state.sel.size > 0 && state.sel.size < state.files.length;
    }
    var bytes = 0;
    state.files.forEach(function (f) { if (state.sel.has(f.id)) bytes += Number(f.size) || 0; });
    var info = state.sel.size ? '已选 ' + state.sel.size + ' 项 · ' + fmtSize(bytes) : '未选择文件';
    var si = $('selInfo');
    if (si) si.textContent = info;
    var z = $('zipBtn');
    if (z) z.disabled = state.sel.size === 0;
    var d = $('delBtn');
    if (d) d.disabled = state.sel.size === 0;
  }

  function toggle(id, on) {
    if (on) state.sel.add(id); else state.sel.delete(id);
    var row = document.querySelector('.frow[data-id="' + id + '"]');
    if (row) row.classList.toggle('sel', !!on);
    updateSelUI();
  }

  /* ---------- 数据加载 ---------- */
  function loadFiles() {
    return api('/api/files').then(function (data) {
      skew = Date.now() / 1000 - data.now;
      state.files = data.files || [];
      state.meta = data;
      var alive = {};
      state.files.forEach(function (f) { alive[f.id] = 1; });
      state.sel.forEach(function (id) { if (!alive[id]) state.sel.delete(id); });
      renderAll();
    }).catch(function (err) { console.warn('列表加载失败', err); });
  }

  function loadInfo() {
    return api('/api/info').then(function (info) {
      state.info = info;
      renderChips();
      return info;
    });
  }

  function removeIds(ids) {
    if (!ids.length) return;
    var tip = ids.length === 1 ? '确定删除这个文件？' : '确定删除选中的 ' + ids.length + ' 个文件？';
    if (!confirm(tip + ' 删除后无法恢复，其他人也将无法下载。')) return;
    api('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids }),
    }).then(function (res) {
      ids.forEach(function (id) { state.sel.delete(id); });
      toast('已删除 ' + (res.deleted || ids.length) + ' 个文件');
      return loadFiles();
    }).catch(function (err) { toast(err.message, true); });
  }

  function downloadZip() {
    var ids = Array.from(state.sel);
    if (!ids.length) return;
    toast('正在打包 ' + ids.length + ' 个文件，浏览器将开始下载…');
    location.href = '/zip?ids=' + ids.join(',');
  }

  /* ---------- 上传 ---------- */
  function uploadOne(file, onProgress) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      var url = '/api/upload?name=' + encodeURIComponent(file.name) + '&mime=' + encodeURIComponent(file.type || '');
      xhr.open('PUT', url, true);
      xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name));
      xhr.upload.onprogress = function (e) {
        if (e.lengthComputable) onProgress(e.loaded / e.total, e.loaded, e.total);
      };
      xhr.onload = function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = {}; }
        if (xhr.status >= 200 && xhr.status < 300 && data.ok) resolve(data.file);
        else reject(new Error(data.error || ('上传失败 HTTP ' + xhr.status)));
      };
      xhr.onerror = function () { reject(new Error('网络中断，上传失败')); };
      xhr.ontimeout = function () { reject(new Error('上传超时')); };
      xhr.timeout = 0;
      xhr.send(file);
    });
  }

  function queueItem(file) {
    var box = $('queue');
    if (box) box.hidden = false;
    var el = mk('div', 'qitem');
    var head = mk('div', 'qhead');
    var nm = mk('span', 'qname', file.name);
    nm.title = file.name;
    var st = mk('span', 'qstat', '等待中');
    head.appendChild(nm);
    head.appendChild(st);
    el.appendChild(head);
    var bar = mk('div', 'bar');
    var fill = mk('i');
    bar.appendChild(fill);
    el.appendChild(bar);
    if (box) box.appendChild(el);

    var base = ' · ' + fmtSize(file.size);
    return {
      el: el,
      progress: function (p, loaded) {
        fill.style.width = Math.round(p * 100) + '%';
        st.textContent = (p >= 1 ? '处理中' : Math.round(p * 100) + '%') + base + (loaded ? '' : '');
      },
      done: function () {
        el.classList.add('done');
        fill.style.width = '100%';
        st.textContent = '已上传' + base;
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 1800);
      },
      fail: function (msg) {
        el.classList.add('err');
        fill.style.width = '100%';
        st.textContent = '失败';
        var err = mk('div', 'qerr', msg);
        el.appendChild(err);
        var retry = mk('button', 'btn btn-ghost btn-sm', '重试');
        retry.type = 'button';
        retry.style.marginTop = '8px';
        retry.addEventListener('click', function () {
          el.parentNode.removeChild(el);
          enqueueUploads([file]);
        });
        el.appendChild(retry);
      },
    };
  }

  function enqueueUploads(files) {
    var list = Array.prototype.slice.call(files || []).filter(function (f) { return f && f.name; });
    if (!list.length) return;
    var running = 0, idx = 0, pending = list.length;
    var CONC = 2;

    function pump() {
      while (running < CONC && idx < list.length) start(list[idx++]);
      if (pending === 0 && running === 0) {
        state.uploading = 0;
        loadFiles();
      }
    }
    function start(file) {
      running++;
      state.uploading++;
      var item = queueItem(file);
      uploadOne(file, function (p, loaded) { item.progress(p, loaded); })
        .then(function (rec) {
          item.done();
          toast(file.name + ' 上传完成');
          return loadFiles();
        })
        .catch(function (err) { item.fail(err.message); })
        .then(function () {
          running--; pending--; state.uploading--;
          pump();
        });
    }
    pump();
  }

  /* ---------- 二维码 ---------- */
  function setupQr() {
    var img = $('qrImg');
    if (!img) return;
    loadInfo().then(function (info) {
      var hn = location.hostname;
      var base = location.origin;
      if ((hn === 'localhost' || hn === '127.0.0.1' || hn === '::1' || hn === '0.0.0.0') && info.lan_urls && info.lan_urls.length) {
        base = info.lan_urls[0];
      }
      var url = base + '/m';
      img.src = '/api/qr.png?url=' + encodeURIComponent(url);
      img.alt = '手机扫码上传：' + url;
      var code = $('qrUrl');
      if (code) code.textContent = url;
      var state_ = $('qrState');
      if (state_) state_.textContent = '手机连同一个 Wi-Fi，扫码打开上传页';
      var cb = $('copyBtn');
      if (cb) cb.addEventListener('click', function () { copyText(url); });
      var hint = $('lanHint');
      if (hint) {
        var others = (info.lan_urls || []).filter(function (u) { return u !== base; }).slice(0, 2);
        hint.textContent = others.length ? '如果扫码打不开，可试试：' + others.join('  ') : '';
      }
    }).catch(function (err) {
      var state_ = $('qrState');
      if (state_) state_.textContent = '二维码加载失败：' + err.message;
    });
  }

  /* ---------- 交互绑定 ---------- */
  function bind() {
    var pickBtn = $('pickBtn');
    var input = $('fileInput');
    if (pickBtn && input) pickBtn.addEventListener('click', function () { input.click(); });
    var camBtn = $('cameraBtn');
    var camInput = $('cameraInput');
    if (camBtn && camInput) camBtn.addEventListener('click', function () { camInput.click(); });
    [input, camInput].forEach(function (el) {
      if (!el) return;
      el.addEventListener('change', function () {
        if (el.files && el.files.length) enqueueUploads(el.files);
        el.value = '';
      });
    });

    var dz = $('dropzone');
    if (dz && input) dz.addEventListener('click', function () { input.click(); });

    ['dragenter', 'dragover'].forEach(function (ev) {
      window.addEventListener(ev, function (e) {
        if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') < 0) return;
        e.preventDefault();
        document.body.classList.add('dragging');
        if (dz) dz.classList.add('hot');
      });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      window.addEventListener(ev, function (e) {
        if (ev === 'drop') e.preventDefault();
        document.body.classList.remove('dragging');
        if (dz) dz.classList.remove('hot');
      });
    });
    window.addEventListener('drop', function (e) {
      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
        e.preventDefault();
        enqueueUploads(e.dataTransfer.files);
      }
    });
    window.addEventListener('paste', function (e) {
      var items = (e.clipboardData && e.clipboardData.files) || [];
      if (items.length) { e.preventDefault(); enqueueUploads(items); }
    });

    var selAll = $('selectAll');
    if (selAll) selAll.addEventListener('change', function () {
      state.files.forEach(function (f) {
        if (selAll.checked) state.sel.add(f.id); else state.sel.delete(f.id);
      });
      renderList();
    });
    var zipBtn = $('zipBtn');
    if (zipBtn) zipBtn.addEventListener('click', downloadZip);
    var delBtn = $('delBtn');
    if (delBtn) delBtn.addEventListener('click', function () { removeIds(Array.from(state.sel)); });
    var refreshBtn = $('refreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', function () {
      loadFiles().then(function () { toast('列表已刷新'); });
    });
  }

  function start() {
    bind();
    setupQr();
    loadFiles();
    setInterval(function () {
      if (!state.uploading) loadFiles();
    }, 15000);
    setInterval(function () {
      if (state.files.length) renderList();
    }, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();
