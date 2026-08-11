/*
 * cropper-upload.js — 全站图片上传裁切（一次封装，通用）
 *
 * 用法：给任意 <input type="file"> 加 data-crop 即可启用裁切；
 *      用 data-ratio 指定裁切比例：
 *        "16/9" 封面图 / Hero 图
 *        "3/2"  案例图 / 业务配图
 *        "1/1"  Logo / 头像
 *        "21/9" 通栏背景
 *        不写    自由裁切
 * 选择文件后弹出裁切框，确认后把裁切结果连同表单其它字段 POST 到原 action。
 * 依赖 Cropper.js（CDN 引入，需在本题脚本前加载）。
 */
(function () {
  'use strict';

  var modal = document.getElementById('cropper-modal');
  if (!modal) return; // 当前页面没有裁切模态框，直接退出

  var img = document.getElementById('cropper-img');
  var confirmBtn = modal.querySelector('.cropper-confirm');
  var cancelBtn = modal.querySelector('.cropper-cancel');
  var closeBtn = modal.querySelector('.cropper-close');
  var errorEl = modal.querySelector('.cropper-modal__error');

  var cropper = null;
  var activeInput = null; // 触发裁切的 <input type="file">
  var pendingFile = null; // 用户选中的原始文件

  // 与后端一致的友好前端提示（后端为权威校验）
  var MAX_BYTES = 5 * 1024 * 1024;
  var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

  function parseRatio(attr) {
    if (!attr) return NaN; // 自由裁切
    var parts = attr.split('/');
    if (parts.length === 2) {
      var a = parseFloat(parts[0]);
      var b = parseFloat(parts[1]);
      if (b) return a / b;
    }
    return NaN;
  }

  function setError(msg) {
    if (errorEl) errorEl.textContent = msg || '';
  }

  function openModal(input, file) {
    activeInput = input;
    pendingFile = file;

    var reader = new FileReader();
    reader.onload = function (e) {
      img.src = e.target.result;
      modal.hidden = false;
      if (cropper) { cropper.destroy(); cropper = null; }
      cropper = new Cropper(img, {
        aspectRatio: parseRatio(input.getAttribute('data-ratio')),
        viewMode: 1,
        autoCropArea: 1,
        background: false,
        responsive: true
      });
      if (confirmBtn) confirmBtn.disabled = false;
      setError('');
    };
    reader.onerror = function () {
      setError('读取文件失败，请重试');
    };
    reader.readAsDataURL(file);
  }

  function closeModal() {
    if (cropper) { cropper.destroy(); cropper = null; }
    modal.hidden = true;
    img.src = '';
    // 清空原始选择，避免原生 submit 再次上传未裁切文件
    if (activeInput) { activeInput.value = ''; }
    activeInput = null;
    pendingFile = null;
    setError('');
  }

  function outputTypeFor(originalType) {
    if (originalType === 'image/png') return 'image/png';
    if (originalType === 'image/webp') return 'image/webp';
    return 'image/jpeg';
  }

  function upload() {
    if (!cropper || !activeInput || !pendingFile) return;
    var input = activeInput;
    var form = input.form;
    if (!form || !form.action) { closeModal(); return; }

    if (confirmBtn) confirmBtn.disabled = true;
    setError('裁切上传中…');

    var canvas = cropper.getCroppedCanvas({
      maxWidth: 1920,
      imageSmoothingEnabled: true,
      imageSmoothingQuality: 'high'
    });
    if (!canvas) {
      setError('裁切失败，请重试');
      if (confirmBtn) confirmBtn.disabled = false;
      return;
    }

    var outType = outputTypeFor(pendingFile.type);
    var ext = outType === 'image/png' ? '.png' : outType === 'image/webp' ? '.webp' : '.jpg';
    var quality = outType === 'image/jpeg' ? 0.92 : undefined;
    // 沿用原文件名（去掉旧扩展名），保证后端 UUID 重命名前文件名可读
    var baseName = (pendingFile.name || 'image').replace(/\.[^.]+$/, '');
    var fileName = baseName + ext;

    canvas.toBlob(function (blob) {
      if (!blob) {
        setError('生成图片失败，请重试');
        if (confirmBtn) confirmBtn.disabled = false;
        return;
      }
      var croppedFile = new File([blob], fileName, { type: outType });

      // 收集表单其它字段，仅用裁切后的文件替换该 input 的值
      var fd = new FormData(form);
      fd.delete(input.name);
      fd.append(input.name, croppedFile, fileName);

      fetch(form.action, {
        method: 'post',
        body: fd,
        credentials: 'same-origin'
      }).then(function (res) {
        if (!res.ok) {
          // 413 / 400 等由后端校验返回
          return res.text().then(function (t) {
            throw new Error('HTTP ' + res.status + (t ? ' ' + t.slice(0, 80) : ''));
          });
        }
        closeModal();
        window.location.reload(); // 刷新以显示新图片预览
      }).catch(function (err) {
        setError('上传失败：' + err.message);
        if (confirmBtn) confirmBtn.disabled = false;
      });
    }, outType, quality);
  }

  function bindInputs(root) {
    var inputs = root.querySelectorAll('input[type="file"][data-crop]');
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.__cropBound) return;
      input.__cropBound = true;

      input.addEventListener('change', function () {
        var file = input.files && input.files[0];
        if (!file) return;
        // 前端友好校验（后端为权威）
        if (ALLOWED.indexOf(file.type) === -1) {
          alert('仅支持 JPG / PNG / WebP 格式');
          input.value = '';
          return;
        }
        if (file.size > MAX_BYTES) {
          alert('文件过大，请上传 ≤ 5MB 的图片');
          input.value = '';
          return;
        }
        openModal(input, file);
      });

      // 阻止原生未裁切提交：只要该 input 还选着文件就不放行
      var form = input.form;
      if (form) {
        form.addEventListener('submit', function (e) {
          if (input.files && input.files.length > 0) {
            e.preventDefault();
          }
        });
      }
    });
  }

  // 取消 / 关闭 / ESC / 点击遮罩
  if (cancelBtn) cancelBtn.addEventListener('click', closeModal);
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  if (confirmBtn) confirmBtn.addEventListener('click', upload);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });
  modal.addEventListener('click', function (e) {
    if (e.target === modal) closeModal();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { bindInputs(document); });
  } else {
    bindInputs(document);
  }
})();
