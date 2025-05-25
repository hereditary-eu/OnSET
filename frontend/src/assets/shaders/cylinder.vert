in vec3 center;


out vec2 vUv;
out vec3 vPos;
out vec3 vCenter;

flat out vec3 aPos;
void main() {

	vCenter = center.xyz;
	vUv = uv;
	vPos = position;
	aPos = position;
	vec4 localPosition = vec4(position, 1.);
	vec4 worldPosition = modelMatrix * localPosition;
	vec4 viewPosition = viewMatrix * worldPosition;
	vec4 projectedPosition = projectionMatrix * viewPosition; //either orthographic or perspective

	gl_Position = projectedPosition;
	// gl_Position = vec4(position, 1.0);

}
