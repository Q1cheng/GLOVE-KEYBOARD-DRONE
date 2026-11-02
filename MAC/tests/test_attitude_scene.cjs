const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({headless: true,
    ...(process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {})});
  try {
    const page = await browser.newPage({deviceScaleFactor: 2});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    for (const size of [{width: 445, height: 286}, {width: 630, height: 388}, {width: 360, height: 330}]) {
      await page.setViewportSize(size);
      await page.goto(process.env.ATTITUDE_URL || 'http://127.0.0.1:8769');
      await page.waitForFunction(() => window.flightDeckAttitude?.inspect().ready);
      const send = state => page.evaluate(s => {
        window.flightDeckAttitude.update(s);
        return {...window.flightDeckAttitude.inspect(), readings: ['pitch','roll','yaw'].map(n => document.getElementById(n).textContent)};
      }, {valid: true, pitch: 0, roll: 0, yaw: 0, ...state});
      let info = await send({pitch: Math.PI / 6});
      assert(info.nose[1] < -0.49, 'positive pitch must lower nose');
      assert.equal(info.readings[0], '+30.0');
      info = await send({roll: Math.PI / 6});
      assert(info.right[1] < -0.49, 'positive roll must lower right side');
      assert.equal(info.readings[1], '+30.0');
      info = await send({yaw: Math.PI / 2});
      assert(info.nose[0] > 0.99, 'positive yaw must turn nose right');
      assert.equal(info.readings[2], '90.0');
      await page.screenshot({path: `/private/tmp/attitude-yaw-${size.width}.png`});
      info = await send({valid: false, pitch: 1, roll: 1, yaw: 1});
      assert.deepEqual(info.readings, ['--','--','--']);
      assert.deepEqual(info.nose, [0,0,-1]);
      assert.equal(info.vertices, 253140, 'must load actual 84,380-triangle STL');
      await page.screenshot({path: `/private/tmp/attitude-neutral-${size.width}.png`});
      const check = await page.evaluate(() => {
        const api = window.flightDeckAttitude;
        api.update({valid: false});
        const c = document.getElementById('scene'), gl = c.getContext('webgl2');
        const pixels = new Uint8Array(c.width*c.height*4);
        gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
        let bright = 0;
        for(let i=0;i<pixels.length;i+=4) if(Math.max(...pixels.slice(i,i+3))>45) bright++;
        const stage = document.getElementById('stage').getBoundingClientRect();
        const labels = [...document.querySelectorAll('.motor,.forward')].map(e=>{
          const r=e.getBoundingClientRect();
          return r.left>=stage.left && r.right<=stage.right && r.top>=stage.top && r.bottom<=stage.bottom;
        });
        return {bright, labels};
      });
      assert(check.bright>200, 'model canvas must contain rendered geometry, not a blank stage');
      assert(check.labels.every(Boolean), 'all fixed labels must remain within the stage');
      console.log('PASS', size, check);
    }
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch(error => {console.error(error); process.exitCode=1;});
