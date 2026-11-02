const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{})});
  try {
    const page=await browser.newPage({viewport:{width:454,height:376},deviceScaleFactor:2});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(process.env.GPS_URL || 'http://127.0.0.1:8770');
    const payload={position:[51.501,-.141],heading:84,distance:46,bearing:312,
      history:[[51.5007,-.1417,1],[51.5008,-.1415,1],[51.50085,-.1412,1],[51.501,-.141,1]],segment:1};
    const update=state=>page.evaluate(s=>{window.flightDeckGPS.update(s);return window.flightDeckGPS.inspect();},state);
    let result=await update(payload);
    assert.equal(result.degrees,'084\u00b0'); assert.equal(result.cardinal,'E');
    assert.equal(result.headingRotation,'rotate(84deg)');
    assert.equal(result.markerRotation,'rotate(84deg)');
    assert.equal(result.bearing,'312\u00b0'); assert.equal(result.homeMarker,false);
    await page.waitForFunction(()=>window.flightDeckGPS.inspect().tileState==='ready',{},{timeout:25000});
    await page.screenshot({path:'/private/tmp/gps-map-live.png'});
    assert(result.scale.meters>0 && result.scale.pixels>0);
    const scaleCheck=await page.evaluate(()=>{
      const s=window.flightDeckGPS.inspect().scale,y=map.getSize().y/2;
      const measured=map.distance(map.containerPointToLatLng([0,y]),map.containerPointToLatLng([s.pixels,y]));
      return Math.abs(measured-s.meters)/s.meters;
    });
    assert(scaleCheck<.01,'scale distance must match the actual map projection');
    await page.evaluate(()=>map.setZoom(16,{animate:false}));
    const zoomed=await page.evaluate(()=>window.flightDeckGPS.inspect().scale);
    assert.equal(zoomed.zoom,16);
    assert.notEqual(zoomed.meters,result.scale.meters,'zoom must change the metric scale');
    await page.evaluate(()=>map.setZoom(17,{animate:false}));
    result=await update({...payload,heading:null});
    assert.equal(result.degrees,'--'); assert.equal(result.cardinal,'--');
    assert.equal(await page.locator('.drone-arrow').evaluate(e=>getComputedStyle(e).display),'none');
    result=await update({...payload,position:null,heading:null,distance:null,bearing:null});
    assert.equal(result.marker,null); assert.equal(result.bearing,'--');
    await page.screenshot({path:'/private/tmp/gps-map-stale.png'});
    result=await update({...payload,position:[51.5012,-.1408],history:[...payload.history,[51.5012,-.1408,2]],segment:2});
    assert.equal(result.trail.length,2,'no line bridging an unavailable position gap');
    const last=result.trail.at(-1).at(-1);
    assert.equal(last.lat,51.5012); assert.equal(last.lng,-.1408);
    for(const size of [{width:360,height:330},{width:650,height:480}]) {
      await page.setViewportSize(size); await page.waitForTimeout(500);
      assert(await page.locator('.heading-display').evaluate(e=>e.getBoundingClientRect().right<=innerWidth));
      assert(await page.locator('#scale').evaluate(e=>e.getBoundingClientRect().bottom<=innerHeight));
      assert(await page.locator('.home-readings').evaluate(e=>e.getBoundingClientRect().right<document.getElementById('scale').getBoundingClientRect().left));
    }
    await page.route('https://**/MapServer/tile/**',r=>r.abort());
    await page.reload();
    await update(payload);
    await page.waitForFunction(()=>window.flightDeckGPS.inspect().tileState==='failed');
    assert((await page.locator('#availability').innerText()).includes('MAP UNAVAILABLE'));
    assert.equal(await page.locator('#bearing').innerText(),'312\u00b0');
    assert.equal(await page.locator('#degrees').innerText(),'084\u00b0');
    await page.screenshot({path:'/private/tmp/gps-map-tiles-unavailable.png'});
    assert.deepEqual(errors,[]);
    console.log('PASS real satellite tiles, yaw, distinct home bearing, history, gaps, invalid state, scale, overlays, missing tiles');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
