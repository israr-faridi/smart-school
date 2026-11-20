const form = document.querySelector('#checkin');
const room = document.querySelector('#checkin-class');
const video = form.querySelector('video');
const canvas = form.querySelector('canvas');
const preview = document.querySelector('#preview');
const status = document.querySelector('#capture-status');
const submit = document.querySelector('#submit-checkin');
const capture = document.querySelector('#take-photo');
const inputs = form.elements;
let stream;
let cameraRequest = 0;

function update(message) {
  status.textContent = message;
  submit.disabled = !(room.value && inputs.qr.value && inputs.gps.value && inputs.capture.value);
}

function stopCamera() {
  cameraRequest++;
  stream?.getTracks().forEach(track => track.stop());
  stream = undefined;
  video.srcObject = null;
  video.hidden = true;
  capture.disabled = true;
}

function clearCapture() {
  inputs.capture.value = '';
  inputs.snapshot.value = '';
  preview.hidden = true;
}

room.addEventListener('change', () => {
  stopCamera();
  clearCapture();
  inputs.qr.value = '';
  inputs.gps.value = '';
  update('Run the QR and GPS simulation for this classroom.');
});

document.querySelector('#scan').addEventListener('click', () => {
  inputs.qr.value = room.selectedOptions[0]?.dataset.qr || '';
  inputs.gps.value = inputs.qr.value ? 'inside' : '';
  update(inputs.qr.value ? 'Demo QR matched. Simulated GPS is inside the classroom zone.' : 'Select an assigned classroom first.');
});

document.querySelector('#start-camera').addEventListener('click', async () => {
  stopCamera();
  clearCapture();
  update('Opening the camera…');
  const request = cameraRequest;
  try {
    const acquired = await navigator.mediaDevices.getUserMedia({video: {width: {ideal: 640}}, audio: false});
    if (request !== cameraRequest) {
      acquired.getTracks().forEach(track => track.stop());
      return;
    }
    stream = acquired;
    video.srcObject = stream;
    video.hidden = false;
    await video.play();
    if (request !== cameraRequest) return;
    capture.disabled = false;
    update('Camera ready. Capture a photo to continue.');
  } catch {
    if (request !== cameraRequest) return;
    stopCamera();
    update('Camera unavailable. Use the demo snapshot to continue.');
  }
});

capture.addEventListener('click', () => {
  if (!video.videoWidth) return;
  canvas.width = Math.min(640, video.videoWidth);
  canvas.height = Math.round(canvas.width * video.videoHeight / video.videoWidth);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  inputs.snapshot.value = canvas.toDataURL('image/jpeg', 0.72);
  inputs.capture.value = 'live';
  preview.src = inputs.snapshot.value;
  preview.hidden = false;
  stopCamera();
  update('Live snapshot captured.');
});

document.querySelector('#demo-photo').addEventListener('click', () => {
  stopCamera();
  clearCapture();
  inputs.capture.value = 'simulated';
  update('Demo snapshot selected. The approval queue will label it as simulated.');
});
form.addEventListener('submit', stopCamera);
window.addEventListener('pagehide', stopCamera);
