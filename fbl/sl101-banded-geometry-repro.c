/* Host-only EGL/GLES2 pixel oracle; no KMS or device access.
 * cc -O2 -Wall -Wextra fbl/sl101-banded-geometry-repro.c -o /tmp/geometry $(pkg-config --cflags --libs egl glesv2) -lm
 * EGL_PLATFORM=surfaceless LIBGL_ALWAYS_SOFTWARE=1 /tmp/geometry 20 12 indexed
 */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static GLuint compile(GLenum type,const char *code) {
 GLuint s=glCreateShader(type); GLint ok=0; glShaderSource(s,1,&code,0); glCompileShader(s);
 glGetShaderiv(s,GL_COMPILE_STATUS,&ok); if(!ok) {char log[1024]={0};glGetShaderInfoLog(s,sizeof(log),0,log);fprintf(stderr,"%s\n",log);exit(2);}return s;
}
int main(int argc,char **argv) {
 if(argc!=4) return 2;
 int stride=atoi(argv[1]),offset=atoi(argv[2]),indexed=!strcmp(argv[3],"indexed");
 if((stride!=8&&stride!=16&&stride!=20&&stride!=32)||offset<0||offset+8>stride||(strcmp(argv[3],"indexed")&&strcmp(argv[3],"arrays")))return 2;
 EGLDisplay d=eglGetDisplay(EGL_DEFAULT_DISPLAY);EGLint maj,min,n=0;
 if(d==EGL_NO_DISPLAY||!eglInitialize(d,&maj,&min)){fprintf(stderr,"EGL unavailable\n");return 77;}
 EGLConfig config;const EGLint conf[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES2_BIT,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
 if(!eglChooseConfig(d,conf,&config,1,&n)||n!=1)return 77;
 const EGLint pb[]={EGL_WIDTH,128,EGL_HEIGHT,128,EGL_NONE},cv[]={EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
 eglBindAPI(EGL_OPENGL_ES_API);EGLSurface surface=eglCreatePbufferSurface(d,config,pb);
 EGLContext ctx=eglCreateContext(d,config,EGL_NO_CONTEXT,cv);
 if(surface==EGL_NO_SURFACE||ctx==EGL_NO_CONTEXT||!eglMakeCurrent(d,surface,surface,ctx))return 77;
 GLuint vs=compile(GL_VERTEX_SHADER,"attribute vec2 a; uniform mat4 m; void main(){gl_Position=m*vec4(a,0.,1.);}");
 GLuint fs=compile(GL_FRAGMENT_SHADER,"precision mediump float; void main(){gl_FragColor=vec4(1.,0.4,0.1,1.);}");
 GLuint program=glCreateProgram();glAttachShader(program,vs);glAttachShader(program,fs);glBindAttribLocation(program,0,"a");glLinkProgram(program);
 GLint linked=0;glGetProgramiv(program,GL_LINK_STATUS,&linked);if(!linked)return 2;glUseProgram(program);
 float c=cosf(0.5235987756f)*0.68f,s=sinf(0.5235987756f)*0.68f;
 const GLfloat mat[16]={c,s,0,0,-s,c,0,0,0,0,1,0,0,0,0,1};
 glUniformMatrix4fv(glGetUniformLocation(program,"m"),1,GL_FALSE,mat);
 const float p[4][2]={{-0.6f,-0.6f},{0.6f,-0.6f},{0.6f,0.6f},{-0.6f,0.6f}};
 unsigned char vertices[128]={0};for(int i=0;i<4;i++)memcpy(vertices+i*stride+offset,p[i],8);
 GLuint vb;glGenBuffers(1,&vb);glBindBuffer(GL_ARRAY_BUFFER,vb);glBufferData(GL_ARRAY_BUFFER,4*stride,vertices,GL_STATIC_DRAW);
 glEnableVertexAttribArray(0);glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,stride,(const void *)(uintptr_t)offset);
 glViewport(0,0,128,128);glDisable(GL_DEPTH_TEST);glDisable(GL_BLEND);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
 if(indexed){const GLushort ix[]={0,1,2,0,2,3};GLuint ib;glGenBuffers(1,&ib);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,ib);glBufferData(GL_ELEMENT_ARRAY_BUFFER,sizeof(ix),ix,GL_STATIC_DRAW);glDrawElements(GL_TRIANGLES,6,GL_UNSIGNED_SHORT,0);}
 else glDrawArrays(GL_TRIANGLE_FAN,0,4);
 unsigned char px[128*128*4];glReadPixels(0,0,128,128,GL_RGBA,GL_UNSIGNED_BYTE,px);
 GLenum e=glGetError();if(e){fprintf(stderr,"GL error 0x%x\n",e);return 3;}
 uint64_t hash=UINT64_C(14695981039346656037);unsigned filled=0;
 for(size_t i=0;i<sizeof(px);i++){hash^=px[i];hash*=UINT64_C(1099511628211);}
 for(size_t i=0;i<sizeof(px);i+=4)if(px[i]||px[i+1]||px[i+2])filled++;
 printf("stride=%d offset=%d indexed=%d filled=%u fnv=%016llx\n",stride,offset,indexed,filled,(unsigned long long)hash);
 eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);eglDestroyContext(d,ctx);eglDestroySurface(d,surface);eglTerminate(d);
 return filled>1000?0:4;
}
