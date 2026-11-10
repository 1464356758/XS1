// Entry list: author's 2026-10-24 comparison (42) + Dianzhong from trial plan.
// App MAU is a dated traffic reference, never a channel rank or income estimate.
import {normalizeSearch} from './search.mjs';
export const PLATFORM_CATALOG_DATE='2026-10-24';
export const PLATFORM_HEAT=Object.freeze({month:'2026-02',checked_at:'2026-10-31',metric:'阅读 App 月活跃用户（万）',source:'QuestMobile《2026短剧行业洞察报告》',url:'https://www.questmobile.com.cn/research/report/2041710682848727041/',table_url:'https://pdf.dfcfw.com/pdf/H3_AP202605271822903507_1.pdf#page=5'});
export const PLATFORMS=Object.freeze([
  {
    "id": "qimao",
    "name": "七猫中文网",
    "type": "综合长篇",
    "aliases": [
      "七猫",
      "qimao"
    ],
    "writer_url": "https://zhushou.qimao.com/",
    "heat": {
      "rank": 2,
      "mau_wan": 8610,
      "app": "七猫免费小说"
    }
  },
  {
    "id": "qimiao",
    "name": "奇妙小说网",
    "type": "综合长篇",
    "aliases": [
      "奇妙",
      "qimiao"
    ],
    "writer_url": "https://zhushou.qimao.com/",
    "heat": null
  },
  {
    "id": "zongheng",
    "name": "纵横中文网",
    "type": "男频综合长篇",
    "aliases": [
      "纵横",
      "zongheng"
    ],
    "writer_url": "https://author.zongheng.com/",
    "heat": null
  },
  {
    "id": "zongheng_female",
    "name": "纵横女生网（原花语）",
    "type": "女频长篇",
    "aliases": [
      "花语",
      "纵横女频",
      "huayu"
    ],
    "writer_url": "https://author.zongheng.com/",
    "heat": null
  },
  {
    "id": "17k",
    "name": "17K小说网",
    "type": "综合长篇及短篇",
    "aliases": [
      "17k",
      "十七K"
    ],
    "writer_url": "https://author.17k.com/",
    "heat": null
  },
  {
    "id": "tadu",
    "name": "塔读小说",
    "type": "综合长篇及短篇",
    "aliases": [
      "塔读",
      "tadu"
    ],
    "writer_url": "https://author.tadu.com/",
    "heat": null
  },
  {
    "id": "shuqi",
    "name": "书旗小说",
    "type": "综合长篇",
    "aliases": [
      "书旗",
      "shuqi"
    ],
    "writer_url": "https://write.shuqi.com/",
    "heat": {
      "rank": 6,
      "mau_wan": 1920,
      "app": "书旗小说"
    }
  },
  {
    "id": "douban",
    "name": "豆瓣阅读",
    "type": "类型长篇／中短篇",
    "aliases": [
      "豆瓣",
      "douban"
    ],
    "writer_url": "https://read.douban.com/",
    "heat": null
  },
  {
    "id": "fanqie",
    "name": "番茄小说（长篇）",
    "type": "免费长篇",
    "aliases": [
      "番茄",
      "番茄免费小说",
      "fanqie"
    ],
    "writer_url": "https://fanqienovel.com/",
    "heat": {
      "rank": 1,
      "mau_wan": 25988,
      "app": "番茄免费小说"
    }
  },
  {
    "id": "fanqie_short",
    "name": "番茄短故事",
    "type": "短篇专项入口",
    "aliases": [
      "番茄短篇",
      "短故事"
    ],
    "writer_url": "https://fanqienovel.com/",
    "heat": null
  },
  {
    "id": "qidian",
    "name": "起点中文网（男频）",
    "type": "付费长篇",
    "aliases": [
      "起点",
      "起点读书",
      "qidian"
    ],
    "writer_url": "https://write.qq.com/portal/introjection",
    "heat": {
      "rank": 5,
      "mau_wan": 1936,
      "app": "起点读书"
    }
  },
  {
    "id": "qidian_female",
    "name": "起点女生网",
    "type": "女频付费长篇",
    "aliases": [
      "起点女频",
      "起女"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": null
  },
  {
    "id": "qqread",
    "name": "QQ阅读（创世／云起相关方向）",
    "type": "男女频综合",
    "aliases": [
      "QQ阅读",
      "创世",
      "云起",
      "qqread"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": {
      "rank": 4,
      "mau_wan": 2680,
      "app": "QQ阅读"
    }
  },
  {
    "id": "kunlun",
    "name": "昆仑中文网（阅文渠道方向）",
    "type": "渠道向长篇",
    "aliases": [
      "昆仑",
      "阅文渠道"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": null
  },
  {
    "id": "xiaoxiang",
    "name": "潇湘书院",
    "type": "女频长篇",
    "aliases": [
      "潇湘",
      "xxsy"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": null
  },
  {
    "id": "hongxiu",
    "name": "红袖添香",
    "type": "女频长篇",
    "aliases": [
      "红袖",
      "hx"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": null
  },
  {
    "id": "jiutian",
    "name": "九天中文网（阅文新媒体方向）",
    "type": "新媒体长篇",
    "aliases": [
      "九天",
      "新媒体"
    ],
    "writer_url": "https://write.qq.com/",
    "heat": null
  },
  {
    "id": "zhangyue",
    "name": "掌阅／掌阅文学（含板栗公开入口）",
    "type": "综合长篇",
    "aliases": [
      "掌阅",
      "ireader",
      "板栗",
      "zhangyue"
    ],
    "writer_url": "https://banli.zhangyue.com/help",
    "heat": {
      "rank": 3,
      "mau_wan": 4090,
      "app": "掌阅"
    }
  },
  {
    "id": "fengdu",
    "name": "疯读小说",
    "type": "免费长篇",
    "aliases": [
      "疯读",
      "fengdu"
    ],
    "writer_url": "https://www.fengduxiaoshuo.com/writer/index.html",
    "heat": null
  },
  {
    "id": "faloo",
    "name": "飞卢小说网",
    "type": "快节奏男频／轻小说",
    "aliases": [
      "飞卢",
      "faloo"
    ],
    "writer_url": "https://b.faloo.com/AuthorLogin.aspx",
    "heat": null
  },
  {
    "id": "zhulang",
    "name": "逐浪小说网",
    "type": "综合长篇",
    "aliases": [
      "逐浪",
      "zhulang"
    ],
    "writer_url": "https://www.zhulang.com/",
    "heat": null
  },
  {
    "id": "heiyan",
    "name": "黑岩阅读",
    "type": "男频／悬疑／都市",
    "aliases": [
      "黑岩",
      "heiyan"
    ],
    "writer_url": "https://www.heiyan.com/",
    "heat": null
  },
  {
    "id": "ruochu",
    "name": "若初文学",
    "type": "女频长篇",
    "aliases": [
      "若初",
      "ruochu"
    ],
    "writer_url": "https://www.ruochu.com/",
    "heat": null
  },
  {
    "id": "hongshu",
    "name": "红薯中文网",
    "type": "男女频长篇",
    "aliases": [
      "红薯",
      "hongshu"
    ],
    "writer_url": "https://i.hongshu.com/",
    "heat": null
  },
  {
    "id": "motie",
    "name": "磨铁文学／来看中文网相关入口",
    "type": "类型长篇／IP",
    "aliases": [
      "磨铁",
      "来看",
      "motie"
    ],
    "writer_url": "https://www.motie.com/",
    "heat": null
  },
  {
    "id": "migu",
    "name": "咪咕文学／咪咕阅读",
    "type": "综合长篇／IP",
    "aliases": [
      "咪咕",
      "cmread",
      "migu"
    ],
    "writer_url": "https://www.cmread.com/wenxuenew/",
    "heat": null
  },
  {
    "id": "iqiyi",
    "name": "爱奇艺小说／爱奇艺文学",
    "type": "类型长篇／影视IP",
    "aliases": [
      "爱奇艺",
      "iqiyi"
    ],
    "writer_url": "https://writer.iqiyi.com/",
    "heat": null
  },
  {
    "id": "jinjiang",
    "name": "晋江文学城",
    "type": "女频／言情／纯爱／类型文",
    "aliases": [
      "晋江",
      "jjwxc"
    ],
    "writer_url": "https://www.jjwxc.net/",
    "heat": null
  },
  {
    "id": "changpei",
    "name": "长佩文学",
    "type": "纯爱／女频／类型文",
    "aliases": [
      "长佩",
      "gongzicp",
      "cp"
    ],
    "writer_url": "https://www.gongzicp.com/",
    "heat": null
  },
  {
    "id": "shudan",
    "name": "书耽",
    "type": "纯爱／女频",
    "aliases": [
      "书耽",
      "shubl"
    ],
    "writer_url": "https://www.shubl.com/",
    "heat": null
  },
  {
    "id": "hanwujinian",
    "name": "寒武纪年",
    "type": "纯爱／类型长篇",
    "aliases": [
      "寒武",
      "寒武纪年"
    ],
    "writer_url": "https://www.hanwujinian.com/draft-us",
    "heat": null
  },
  {
    "id": "bugu",
    "name": "布咕阅读",
    "type": "纯爱／同人／女频",
    "aliases": [
      "布咕",
      "bgwxc"
    ],
    "writer_url": "https://www.bgwxc.com/",
    "heat": null
  },
  {
    "id": "liancheng",
    "name": "连城读书",
    "type": "女频／纯爱／综合类型",
    "aliases": [
      "连城",
      "lcread"
    ],
    "writer_url": "https://www.lcread.com/",
    "heat": null
  },
  {
    "id": "sfacg",
    "name": "SF轻小说／菠萝包",
    "type": "二次元／轻小说／对话小说",
    "aliases": [
      "SF",
      "菠萝包",
      "sfacg",
      "轻小说"
    ],
    "writer_url": "https://i.sfacg.com/",
    "heat": null
  },
  {
    "id": "ciweimao",
    "name": "刺猬猫阅读",
    "type": "二次元／轻小说",
    "aliases": [
      "刺猬猫",
      "欢乐书客",
      "ciweimao"
    ],
    "writer_url": "https://author-wap.ciweimao.com/",
    "heat": null
  },
  {
    "id": "ciyuanji",
    "name": "次元姬小说",
    "type": "二次元／轻小说",
    "aliases": [
      "次元姬",
      "ciyuanji"
    ],
    "writer_url": "https://www.ciyuanji.com/",
    "heat": null
  },
  {
    "id": "bkneng",
    "name": "不可能的世界／不可能文学",
    "type": "女频／轻小说／类型文",
    "aliases": [
      "不可能",
      "不可能的世界",
      "bkneng"
    ],
    "writer_url": "https://zuozhe.bkneng.com/",
    "heat": null
  },
  {
    "id": "zhihu",
    "name": "知乎盐选／盐言故事",
    "type": "短篇／中篇／类型故事",
    "aliases": [
      "知乎",
      "盐选",
      "盐言",
      "短篇"
    ],
    "writer_url": "https://www.zhihu.com/creator/explore/academy/create/author",
    "heat": null
  },
  {
    "id": "gushi",
    "name": "每天读点故事",
    "type": "短篇／中篇／类型文",
    "aliases": [
      "每天读点故事",
      "每天",
      "gushi"
    ],
    "writer_url": "https://www.gushi.cn/",
    "heat": null
  },
  {
    "id": "huaben",
    "name": "话本小说",
    "type": "对话小说／同人／原创长篇",
    "aliases": [
      "话本",
      "ihuaben"
    ],
    "writer_url": "https://www.ihuaben.com/",
    "heat": null
  },
  {
    "id": "kuaidian",
    "name": "快点阅读",
    "type": "对话／互动故事",
    "aliases": [
      "快点",
      "对话"
    ],
    "writer_url": "https://apps.apple.com/cn/app/id1228112060",
    "entry_note": "附件仅提供应用商店入口，当前投稿入口及官方域名待核。",
    "heat": null
  },
  {
    "id": "qimao_short",
    "name": "七猫短故事",
    "type": "短篇专项入口",
    "aliases": [
      "七猫短篇",
      "短故事"
    ],
    "writer_url": "https://zhushou.qimao.com/",
    "heat": null
  },
  {
    "id": "dianzhong",
    "name": "点众文学",
    "type": "综合长篇／新媒体",
    "aliases": [
      "点众",
      "点众科技",
      "ssread"
    ],
    "writer_url": "https://www.ssread.cn/",
    "heat": null
  }
]);
export const platformByName=name=>PLATFORMS.find(p=>p.name===name)||null;
export function matchesPlatform(platform,query){
  const text=normalizeSearch([platform.name,platform.id,platform.type,...platform.aliases].join(' '));
  return normalizeSearch(query).split(' ').filter(Boolean).every(term=>text.includes(term));
}
export function platformChoices(query='',chosen='',sort='heat'){
  const matches=PLATFORMS.filter(p=>matchesPlatform(p,query)).sort((a,b)=>{
    if(sort==='heat'){
      const delta=(a.heat?.rank??Infinity)-(b.heat?.rank??Infinity);
      if(!Number.isNaN(delta)&&delta!==0)return delta;
    }
    return a.name.localeCompare(b.name,'zh-CN')||a.id.localeCompare(b.id);
  });
  const selected=platformByName(chosen);
  return {matches,selected,retained:selected&&!matches.some(p=>p.id===selected.id)?selected:null};
}
export const platformOptionLabel=p=>(p.heat?'热度 '+p.heat.rank+' · ':'')+p.name;
