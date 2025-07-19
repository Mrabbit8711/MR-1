import os
import discord
from discord.ext import commands
from datetime import datetime, timedelta
import random
import dateparser
from dateparser.search import search_dates
import pytz
import re

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

guild_raid_store = {}
KST = pytz.timezone("Asia/Seoul")

def generate_raid_id():
    return f"#{random.randint(100000, 999999)}"

def get_weekday_kr(dt):
    weekdays = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']
    return weekdays[dt.weekday()]

def get_ampm_kr(dt):
    return "오전" if dt.hour < 12 else "오후"

def extract_time_and_memo(input_str):
    KST = pytz.timezone("Asia/Seoul")
    now = datetime.now(KST)

    # 1. 한글: (오늘|내일)? (오전|오후) N시 [N분]
    m = re.match(r'^\s*((오늘|내일)?\s*(오전|오후)\s*([0-9]{1,2})시\s*([0-9]{1,2})?분?)(.*)', input_str)
    if m:
        date_kw = m.group(2)
        ampm = m.group(3)
        hour = int(m.group(4))
        minute = int(m.group(5)) if m.group(5) else 0
        memo = m.group(6).strip()
        if ampm == "오후" and hour != 12:
            hour += 12
        if ampm == "오전" and hour == 12:
            hour = 0
        base_day = now
        if date_kw == "내일":
            base_day = now + timedelta(days=1)
        raid_dt = base_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # "오늘"이고 이미 지난 시간이면 내일로 넘김
        if (date_kw is None or date_kw == "오늘") and raid_dt < now:
            raid_dt += timedelta(days=1)
        return raid_dt, memo

    # 2. "다음주 월요일 오후 8시 30분" 등 복합 날짜는 dateparser
    search_result = search_dates(
        input_str,
        languages=['ko'],
        settings={
            'TIMEZONE': 'Asia/Seoul',
            'TO_TIMEZONE': 'Asia/Seoul',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
        }
    )
    if search_result:
        time_str, time_dt = search_result[0]
        idx = input_str.find(time_str) + len(time_str)
        memo = input_str[idx:].strip()
        # "분" 없는 경우 정각 보정
        if '분' not in time_str:
            time_dt = time_dt.replace(minute=0, second=0, microsecond=0)
        if time_dt.tzinfo is not None:
            if str(time_dt.tzinfo) in ["UTC", "UTC+00:00"]:
                time_dt = time_dt.astimezone(KST)
        else:
            time_dt = KST.localize(time_dt)
        now = datetime.now(KST)
        if ("오늘" in time_str or "내일" in time_str) and time_dt < now:
            time_dt += timedelta(days=1)
        return time_dt, memo

    # 3. 기타 dateparser 단독 시도
    parse_dt = dateparser.parse(
        input_str,
        languages=['ko'],
        settings={
            'TIMEZONE': 'Asia/Seoul',
            'TO_TIMEZONE': 'Asia/Seoul',
            'RETURN_AS_TIMEZONE_AWARE': True,
            'PREFER_DATES_FROM': 'future',
        }
    )
    if not parse_dt:
        parse_dt = dateparser.parse(
            "오늘 " + input_str,
            languages=['ko'],
            settings={
                'TIMEZONE': 'Asia/Seoul',
                'TO_TIMEZONE': 'Asia/Seoul',
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
            }
        )
    if parse_dt:
        if '분' not in input_str:
            parse_dt = parse_dt.replace(minute=0, second=0, microsecond=0)
        if parse_dt.tzinfo is not None:
            if str(parse_dt.tzinfo) in ["UTC", "UTC+00:00"]:
                parse_dt = parse_dt.astimezone(KST)
        else:
            parse_dt = KST.localize(parse_dt)
        now = datetime.now(KST)
        if parse_dt < now:
            parse_dt += timedelta(days=1)
        return parse_dt, ""
    return None, None

def make_raid_embed(raid, guild=None):
    dt = raid['time']
    weekday_kr = get_weekday_kr(dt)
    ampm_kr = get_ampm_kr(dt)
    hour12 = dt.hour % 12
    if hour12 == 0:
        hour12 = 12
    dt_str = f"{dt.year}-{dt.month:02d}-{dt.day:02d} {weekday_kr} {ampm_kr} {hour12}시{dt.minute:02d}분"
    embed = discord.Embed(title=dt_str, color=discord.Color.blue())
    embed.add_field(name="아이디", value=raid['id'], inline=True)
    embed.add_field(name="최대인원", value=f"{raid['max_member']}명", inline=True)
    member_names = []
    for user_id in raid['members']:
        name = None
        if guild:
            member = guild.get_member(user_id)
            if member:
                name = member.nick if member.nick else member.display_name
        if not name:
            name = f"<@{user_id}>"
        member_names.append(name)
    embed.add_field(name=f"멤버 ({len(raid['members'])}/{raid['max_member']})", value="\n".join(member_names) if member_names else "-", inline=False)
    memo = raid.get('memo', "-")
    embed.add_field(name="메모", value=memo if memo else "-", inline=False)
    embed.add_field(name="변경사항", value=raid['log'][-1], inline=False)
    return embed

class ParticipateView(discord.ui.View):
    def __init__(self, raid, store, ctx):
        super().__init__(timeout=None)
        self.raid = raid
        self.store = store
        self.ctx = ctx

    @discord.ui.button(label="참여/취소", emoji="✅", style=discord.ButtonStyle.success)
    async def participate(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        display_name = None
        if interaction.guild:
            member = interaction.guild.get_member(user_id)
            display_name = member.nick if member and member.nick else interaction.user.display_name
        else:
            display_name = interaction.user.display_name

        if user_id in self.raid['members']:
            self.raid['members'].remove(user_id)
            self.raid['log'].append(f"{display_name} 탈퇴")
        else:
            if len(self.raid['members']) >= self.raid['max_member']:
                await interaction.response.send_message("정원이 다 찼습니다.", ephemeral=True)
                return
            self.raid['members'].append(user_id)
            self.raid['log'].append(f"{display_name} 참가")
        embed = make_raid_embed(self.raid, guild=interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command()
async def 만들기(ctx, *, args):
    raid_time, memo = extract_time_and_memo(args.strip())
    if not raid_time:
        await ctx.send("시간을 이해할 수 없습니다.")
        return
    raid_id = generate_raid_id()
    store = guild_raid_store.setdefault(ctx.guild.id, {})
    store[raid_id] = {
        'id': raid_id,
        'time': raid_time,
        'max_member': 8,
        'members': [],
        'memo': memo,
        'log': ['레이드가 생성되었습니다.']
    }
    embed = make_raid_embed(store[raid_id], guild=ctx.guild)
    view = ParticipateView(store[raid_id], store, ctx)
    await ctx.send(embed=embed, view=view)

@bot.command()
async def 변경(ctx, *, args):
    import re
    m = re.match(r'#(\d{6}),\s*(.+)', args)
    if not m:
        await ctx.send("예시: !변경 #123456, 4명 또는 !변경 #123456, 내일 오후 9시")
        return
    raid_id = f"#{m.group(1)}"
    value = m.group(2).strip()
    store = guild_raid_store.get(ctx.guild.id, {})
    raid = store.get(raid_id)
    if not raid:
        await ctx.send("해당 레이드를 찾을 수 없습니다.")
        return
    if "명" in value:
        try:
            num = int(value.replace("명", "").strip())
            raid['max_member'] = num
            raid['log'].append(f"최대 인원이 {num}명으로 변경됨")
        except:
            await ctx.send("인원 수를 이해할 수 없습니다.")
            return
    else:
        raid_time, _ = extract_time_and_memo(value)
        if not raid_time:
            await ctx.send("시간을 이해할 수 없습니다.")
            return
        raid['time'] = raid_time
        raid['log'].append(f"시간이 {value}로 변경됨")
    embed = make_raid_embed(raid, guild=ctx.guild)
    await ctx.send(embed=embed)

@bot.command()
async def 삭제(ctx, raid_id):
    raid_id = raid_id.strip()
    store = guild_raid_store.get(ctx.guild.id, {})
    if raid_id in store:
        del store[raid_id]
        await ctx.send(f"{raid_id} 레이드가 삭제되었습니다.")
    else:
        await ctx.send("해당 레이드를 찾을 수 없습니다.")

@bot.command()
async def 레이드(ctx, raid_id=None):
    store = guild_raid_store.get(ctx.guild.id, {})
    if raid_id:
        raid = store.get(raid_id.strip())
        if not raid:
            await ctx.send("해당 레이드를 찾을 수 없습니다.")
            return
        embed = make_raid_embed(raid, guild=ctx.guild)
        view = ParticipateView(raid, store, ctx)
        await ctx.send(embed=embed, view=view)
    else:
        if not store:
            await ctx.send("등록된 레이드가 없습니다.")
            return
        for raid in list(store.values())[:5]:
            embed = make_raid_embed(raid, guild=ctx.guild)
            view = ParticipateView(raid, store, ctx)
            await ctx.send(embed=embed, view=view)

@bot.command()
async def 문토끼도움말(ctx):
    msg = (
        "**문토끼 봇 명령어 도움말**\n"
        "`!만들기 오후 10시 30분 메모 내용` - 레이드 생성 (참여/취소 버튼 포함)\n"
        "`!변경 #123456, 4명` - 최대 인원 변경\n"
        "`!변경 #123456, 내일 오후 9시` - 시간 변경\n"
        "`!삭제 #123456` - 레이드 삭제\n"
        "`!레이드 #123456` - 특정 레이드 정보\n"
        "`!레이드` - 전체 레이드 목록\n"
        "참여/취소는 v버튼으로 동작\n"
    )
    ##await ctx.send(msg)

bot.run(os.environ["DISCORD_TOKEN"])
