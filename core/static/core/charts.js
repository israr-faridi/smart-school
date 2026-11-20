const library = document.currentScript || document.querySelector('[data-chart-library]');
const data = JSON.parse(document.querySelector('#chart-data').textContent);

function drawCharts() {
  new Chart(document.querySelector('#results'), {
    type: 'doughnut',
    data: {labels: ['Pass', 'Fail'], datasets: [{data: data.results, backgroundColor: ['#248b73', '#d55c64']}]},
    options: {responsive: true, maintainAspectRatio: false}
  });
  new Chart(document.querySelector('#cashflow'), {
    type: 'line',
    data: {labels: data.labels, datasets: [
      {label: 'Fee inflow', data: data.inflow, borderColor: '#275bde', tension: 0.25},
      {label: 'Payroll outflow', data: data.outflow, borderColor: '#b55023', tension: 0.25}
    ]},
    options: {responsive: true, maintainAspectRatio: false, scales: {y: {beginAtZero: true}}}
  });
}

if (window.Chart) {
  drawCharts();
} else {
  const script = document.createElement('script');
  script.src = library.dataset.chartLibrary;
  script.addEventListener('load', drawCharts);
  document.head.append(script);
}
