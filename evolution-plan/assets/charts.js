// charts.js — 声浪雷达进化方案图表
(function () {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // 初始化 Mermaid
  if (typeof mermaid !== 'undefined') {
    mermaid.initialize({ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' });
  }

  // ===== 图 1:核心能力现状 vs 目标 雷达图 =====
  var radarEl = document.getElementById('chart-radar');
  if (radarEl) {
    var radar = echarts.init(radarEl, null, { renderer: 'svg' });
    radar.setOption({
      animation: false,
      tooltip: { appendToBody: true },
      legend: {
        data: ['现状', '进化目标'],
        top: 8,
        textStyle: { color: ink, fontSize: 13 },
        itemGap: 24
      },
      radar: {
        center: ['50%', '56%'],
        radius: '66%',
        indicator: [
          { name: '多平台覆盖', max: 10 },
          { name: '实时感知', max: 10 },
          { name: '对话交互', max: 10 },
          { name: '多智能体协同', max: 10 },
          { name: '预测能力', max: 10 },
          { name: '闭环执行', max: 10 }
        ],
        axisName: { color: ink, fontSize: 13, fontWeight: 600 },
        splitLine: { lineStyle: { color: rule } },
        splitArea: { areaStyle: { color: [bg2, '#f5f6fa'] } },
        axisLine: { lineStyle: { color: rule } }
      },
      series: [{
        type: 'radar',
        data: [
          {
            value: [4, 3, 2, 4, 2, 3],
            name: '现状',
            areaStyle: { color: 'rgba(107,114,128,0.18)' },
            lineStyle: { color: muted, width: 2 },
            itemStyle: { color: muted },
            symbolSize: 6
          },
          {
            value: [8, 9, 9, 9, 7, 8],
            name: '进化目标',
            areaStyle: { color: 'rgba(0,47,167,0.20)' },
            lineStyle: { color: accent, width: 2.5 },
            itemStyle: { color: accent },
            symbolSize: 7
          }
        ]
      }]
    });
    window.addEventListener('resize', function () { radar.resize(); });
  }

  // ===== 图 3:六方向实施节奏 甘特图 =====
  var ganttEl = document.getElementById('chart-gantt');
  if (ganttEl) {
    var gantt = echarts.init(ganttEl, null, { renderer: 'svg' });
    // 方向名 + 三阶段(周) 起止
    var dirs = [
      'DIR 02 对话式交互层',
      'DIR 01 多智能体协同',
      'DIR 04 实时感知与事件检测',
      'DIR 06 知识沉淀与个性化',
      'DIR 03 跨平台全域聚合',
      'DIR 05 预测性与规范性智能'
    ];
    // [起始周, 持续周数]
    var data = [
      [0, 2], // DIR02 P1
      [1, 3], // DIR01 P1-P2
      [2, 2], // DIR04 P2
      [3, 3], // DIR06 P2-P3
      [2, 3], // DIR03 P2-P3
      [4, 2]  // DIR05 P3
    ];
    var phaseColors = [accent, accent, accent2, accent2, muted, muted];
    var seriesData = data.map(function (d, i) {
      return {
        name: dirs[i],
        value: [i, d[0], d[0] + d[1], d[1]],
        itemStyle: { color: phaseColors[i] }
      };
    });

    gantt.setOption({
      animation: false,
      tooltip: {
        appendToBody: true,
        formatter: function (p) {
          var v = p.value;
          return '<b>' + dirs[v[0]] + '</b><br/>第 ' + (v[1] + 1) + '-' + v[2] + ' 周';
        }
      },
      grid: { left: 200, right: 30, top: 40, bottom: 40 },
      xAxis: {
        type: 'value',
        min: 0,
        max: 6,
        interval: 1,
        name: '周',
        nameLocation: 'end',
        nameTextStyle: { color: muted, fontSize: 12 },
        axisLabel: {
          color: muted,
          formatter: function (v) { return '第' + (v + 1) + '周'; }
        },
        splitLine: { lineStyle: { color: rule, type: 'dashed' } },
        axisLine: { lineStyle: { color: rule } }
      },
      yAxis: {
        type: 'category',
        data: dirs,
        inverse: true,
        axisLabel: { color: ink, fontSize: 12 },
        axisLine: { lineStyle: { color: rule } },
        axisTick: { show: false }
      },
      series: [{
        type: 'custom',
        renderItem: function (params, api) {
          var cat = api.value(0);
          var start = api.coord([api.value(1), cat]);
          var end = api.coord([api.value(2), cat]);
          var height = api.size([0, 1])[1] * 0.5;
          return {
            type: 'rect',
            shape: {
              x: start[0],
              y: start[1] - height / 2,
              width: end[0] - start[0],
              height: height,
              r: 4
            },
            style: api.style()
          };
        },
        encode: { x: [1, 2], y: 0 },
        data: seriesData
      }]
    });
    window.addEventListener('resize', function () { gantt.resize(); });
  }
})();
