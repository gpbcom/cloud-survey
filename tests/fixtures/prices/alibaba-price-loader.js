(function () {

var cssUrls = [
'https://g.alicdn.com/aliyun/www-product-ecs-price/1.0.55/antd.min.css',
'https://g.alicdn.com/aliyun/www-product-ecs-price/1.0.55/index.css'
];
var mainJs = 'https://g.alicdn.com/aliyun/www-product-ecs-price/1.0.55/index.js';
var priceUrls = [
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/instanceTypePrice_1.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/instanceTypePrice_2.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/disk_price/diskPrice.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/bandwidth_price/bandWidthPrice.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/reservedInstancePrice.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/dedicatedHostPrice.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/storageCapacityUnit.js',
'https://g.alicdn.com/aliyun/ecs-price-info-intl/2.0.421/price/js_price/filter_price/instanceTypeDefinition.js'
];

for (var i = 0; i < cssUrls.length; i++) {
var link = document.createElement('link');
link.rel = 'stylesheet';
link.href = cssUrls[i];
document.head.appendChild(link);
}

var remaining = priceUrls.length;
function onDone() {
if (--remaining === 0) {
var bodyScript = document.createElement('script');
bodyScript.type = 'text/javascript';
bodyScript.src = mainJs;
document.body.appendChild(bodyScript);
}
}
for (var j = 0; j < priceUrls.length; j++) {
var script = document.createElement('script');
script.type = 'text/javascript';
script.src = priceUrls[j];
script.onload = onDone;
script.onerror = onDone;
document.body.appendChild(script);
}
})();
