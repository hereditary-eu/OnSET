in vec3 vCenter;
in vec2 vUv;
in vec3 vPos;
flat in vec3 aPos;

uniform float borderRadius;
uniform vec3 borderColor;

float PI = 3.1415926535897932384626433832795;
float PI2 = 6.283185307179586476925286766559;
// uniform float time;
//https://en.wikipedia.org/wiki/HSL_and_HSV#HSL_to_RGB_alternative

float conversion_helper(float n, float h, float s, float l) {
    float k = mod(n + h / 30.0, 12.0);
    float a = s * min(l, 1.0 - l);
    return l - a * max(-1.0, min(k - 3.0, min(9.0 - k, 1.0)));
}

vec3 hsl2rgb(float h, float s, float l) {
    return vec3(conversion_helper(0.0, h, s, l), conversion_helper(8.0, h, s, l), conversion_helper(4.0, h, s, l));
}

void main() {
    //https://github.com/mrdoob/three.js/blob/bc58fecba18150103b95fbde5aaa3cc7cddf95a7/examples/webgl_materials_wireframe.html#L38C1-L41C64
    // vec3 diff = abs(vPos - aPos);
    // vec3 diff = abs(vPos - aPos);
    // float edge = max(diff.x, max(diff.y, diff.z));
    // gl_FragColor = vec4(vCenter, 1.0);
    vec3 afwidth = fwidth(vCenter.xyz);
    vec3 edge3 = smoothstep((borderRadius - 1.0) * afwidth, borderRadius * afwidth, vCenter.xyz);

    float edge = 1.0 - min(min(edge3.x, edge3.y), edge3.z);
    // gl_FragColor.rgb = gl_FrontFacing ? vec3(0.9, 0.9, 1.0) : vec3(0.4, 0.4, 0.5);
    // gl_FragColor.a = edge;

    vec2 planar_pos = vPos.xz;
    float radius = 1.0;
    float height = 1.0;

    float h = atan(planar_pos.y, planar_pos.x) * 360.0 / PI2;
    float s = length(planar_pos) / radius;
    float l = (vPos.y + 0.5) / height;

    if(edge > 0.8) {
        // gl_FragColor = vec4(vec3(1.0), 1.0);
        // return;
        l = 1.0 - l;
    }

    gl_FragColor = vec4(hsl2rgb(h, s, l), 1.0);

}