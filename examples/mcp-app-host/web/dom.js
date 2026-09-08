import {marked} from 'marked';
import DOMPurify from 'dompurify';
export const $=id=>document.getElementById(id);
export function node(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
const paths={spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',arrow:'M12 19V5m-6 6 6-6 6 6',down:'M12 5v14m-6-6 6 6 6-6',plus:'M12 5v14M5 12h14',chevron:'m9 5 7 7-7 7',check:'m5 12 4 4L19 6',tool:'m14 6 4 4M7 17l-2 2m3-7 5-5a4 4 0 0 1 5-5l-3 3 4 4 3-3a4 4 0 0 1-5 5l-5 5a3 3 0 1 1-4-4Z',copy:'M9 9h11v11H9zM15 9V4H4v11h5',close:'m6 6 12 12M6 18 18 6',settings:'M4 7h16M4 17h16M8 4v6m8 4v6',stop:'M7 7h10v10H7z',alert:'M12 8v5m0 3v.1M10 3 2 18a2 2 0 0 0 2 3h16a2 2 0 0 0 2-3L14 3a2 2 0 0 0-4 0Z',chat:'M21 12a8 8 0 0 1-8 8H4l1-5a8 8 0 1 1 16-3Z'};
export function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[name]||paths.spark);svg.append(p);return svg;}
export function button(label,name,cls='icon-button'){const b=node('button',undefined,cls);b.type='button';b.setAttribute('aria-label',label);b.title=label;b.append(icon(name));return b;}
export function markdown(el,text){
  el.innerHTML=DOMPurify.sanitize(marked.parse(text,{async:false,gfm:true,breaks:true}),{
    ALLOWED_TAGS:['p','br','strong','em','del','ul','ol','li','pre','code','blockquote','h1','h2','h3','h4','hr','a','table','thead','tbody','tr','th','td'],
    ALLOWED_ATTR:['href','title'],ALLOW_DATA_ATTR:false,ALLOW_ARIA_ATTR:false,
  });
  for(const link of el.querySelectorAll('a')){
    try{const raw=link.getAttribute('href');if(!raw)throw new Error();const url=new URL(raw,location.href);if(!['https:','http:','mailto:'].includes(url.protocol))throw new Error();link.target='_blank';link.rel='noopener noreferrer';}
    catch{link.removeAttribute('href');}
  }
}
export const toolLabel=(status,name)=>status?.tools.find(tool=>tool.name===name)?.title||name.replaceAll('_',' ').replace(/^\w/,c=>c.toUpperCase());
export const fallback=result=>(result?.content||[]).filter(item=>item.type==='text').map(item=>item.text).join('\n');
export function jsonDetails(title,value){const details=node('details',undefined,'data-details');details.append(node('summary',title),node('pre',JSON.stringify(value,null,2)));return details;}
