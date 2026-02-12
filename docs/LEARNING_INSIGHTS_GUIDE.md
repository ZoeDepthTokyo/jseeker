# Learning Insights Guide

**What you're looking at:** A transparency dashboard that shows how jSeeker gets smarter and cheaper over time.

---

## The Big Picture

Think of jSeeker like a personal assistant learning your preferences. The first time you ask them to do something, they need careful instructions. But after a few times, they remember and can handle it automatically.

**The Learning Insights page shows you this learning process in action.**

---

## What Each Section Means

### 📊 Pattern Learning Stats

**What it shows:**
- **Total Patterns**: How many "recipes" jSeeker has learned for adapting your resume
- **Cache Hit Rate**: What percentage of the time jSeeker reuses old patterns instead of asking AI
- **Cost Saved**: Real dollars saved by reusing patterns instead of making expensive AI calls

**In plain English:**

When you generate a resume, jSeeker adapts your bullet points to match the job description. The first time it sees "Led cross-functional teams," it asks AI how to rewrite it. But then it saves that transformation as a "pattern."

The next time it sees similar text + similar job, it just reuses the pattern. No AI call needed. That's a cache hit.

**What "good" looks like:**
- After 10-20 resumes: **30-40% cache hit rate** (7 out of 10 adaptations are free)
- After 50+ resumes: **60-70% cache hit rate** (most work is free)
- Each cache hit saves ~$0.01-0.03

---

### 💰 Cost Optimization

**What it shows:**
- **Total Spent (This Month)**: How much you've paid for AI calls this month
- **Avg Cost per Resume**: How much each resume costs to generate
- **Cumulative API Costs Over Time**: A graph showing your total spending over time

**Why it matters:**

Your first few resumes are expensive (around $0.15-0.30 each) because jSeeker is learning. After 20-30 resumes, the cost drops to $0.05-0.10 per resume because most adaptations reuse patterns.

**What you're watching for:**

The graph should curve (not a straight line). If it's a straight diagonal, jSeeker isn't learning. If it curves up slowly, that's good—it means each resume is cheaper than the last.

**What "good" looks like:**
- Resume 1-10: $0.20-0.30 per resume
- Resume 20-50: $0.08-0.15 per resume
- Resume 50+: $0.03-0.08 per resume

---

### 📋 Pattern Schema & JSON Rules

**What it shows:**

A technical example of how patterns are stored in the database.

**You probably don't need this section unless:**
- You're debugging something
- You're curious about the internals
- You're a developer

**Skip this unless you're technical.**

---

### 🔄 Pattern History

**What it shows:**

A detailed log of every pattern jSeeker has learned, grouped by type:
- **Bullet Adaptation**: How to rewrite bullet points
- **Summary Style**: How to rewrite your professional summary
- **Skills Matching**: Which skills to emphasize

**Why it's useful:**

You can see **exactly what jSeeker learned** from your past resumes. Each pattern shows:
- **Before**: The original text from your resume block
- **After**: How jSeeker adapted it
- **Used Xx**: How many times this pattern was reused
- **Confidence**: How sure jSeeker is that this pattern works (0.0-1.0)
- **JD Context**: What kind of job this pattern works for (role + keywords)

**What to look for:**

Patterns with high "Used" counts are your workhorses—they're getting reused a lot. Patterns with low confidence (<0.7) might be experimental or only work for niche jobs.

**Charts in this section:**
1. **Pattern Library Growth**: Shows how many patterns you've accumulated over time
2. **Cost Savings from Pattern Reuse**: Breaks down savings by pattern type (bullets vs. summaries, etc.)

---

### 📈 Performance Trends

**What it shows:**

A scatter plot of cost per resume over time. Each dot is one resume.

**The trend line should go DOWN over time.** That's the goal.

**What this tells you:**

- **Downward trend**: jSeeker is learning! Each resume is cheaper than the last.
- **Flat trend**: You're generating very different resumes (different industries, roles), so patterns aren't reusing. That's okay—just means you have diverse needs.
- **Upward trend**: Something's wrong. Either you're tackling harder jobs, or the pattern matching isn't working.

**The dashboard will tell you:**
- ✅ "Cost optimization working! Average cost decreased by X%" (good)
- 📊 "Cost trend is stable." (neutral—you're in steady state)
- ⚠️ "Costs increasing." (rare—might mean you switched industries)

**What "good" looks like:**

If you compare your first 5 resumes to your last 5 resumes, costs should drop by 40-60%.

---

## How the System Actually Learns

Here's the full loop:

1. **You generate a resume**
   jSeeker adapts your bullet points using AI.

2. **The pattern is stored**
   Each adaptation gets saved: "When the job is X and the source text is Y, the adapted text is Z."

3. **You generate another resume**
   jSeeker checks: "Have I seen something like this before?"

4. **Pattern match (cache hit)**
   If yes, it reuses the old pattern. No AI call. Free. Fast.

5. **No match (cache miss)**
   If no, it calls AI again, gets a fresh adaptation, and stores *that* as a new pattern.

6. **Repeat**
   Over time, the pattern library fills up, and more requests become cache hits.

---

## Calibrating Your Expectations

### When jSeeker is "learning well"
- Cache hit rate climbs 5-10% every 10 resumes
- Cost per resume drops by half after 20-30 resumes
- You see patterns with 5+ uses in the Pattern History

### When jSeeker is "learning slowly"
- Cache hit rate stays below 20% after 20 resumes
- Cost per resume stays flat or increases
- You see many patterns with 1-2 uses, few with 5+

**Why might learning be slow?**
- You're applying to very different roles (e.g., "Software Engineer" then "Product Manager" then "Data Analyst")
- Each job has unique keywords that don't overlap
- You're still in the early phase (under 10 resumes)

**This is normal.** jSeeker learns fastest when you apply to similar roles repeatedly.

---

## Common Questions

**Q: I generated 5 resumes and my cache hit rate is 0%. Is something broken?**
A: No. Patterns need to be used at least 3 times before jSeeker trusts them. After 5 resumes, you're still building the library. Check back after 15-20 resumes.

**Q: My cost per resume went UP. Why?**
A: Probably because you switched to a more complex job description (longer JD = more work). Or you used a different template. This is usually temporary.

**Q: What's a "good" cache hit rate?**
A:
- 10 resumes: 10-20% is normal
- 20 resumes: 30-40% is good
- 50 resumes: 60-70% is excellent

**Q: Can I delete old patterns?**
A: Not from the UI (yet). But they don't hurt—unused patterns just sit there. Only high-frequency patterns get reused.

**Q: Why does the "Top 10 Learned Patterns" table show truncated text?**
A: To keep the page readable. The full patterns are in the database and get used correctly—the UI just previews them.

---

## What to Do With This Information

**If you're just starting (under 10 resumes):**
Check the Learning Insights page after every 5 resumes. You should see the pattern library growing and costs stabilizing.

**If you're a power user (50+ resumes):**
Watch the cache hit rate. If it drops below 50%, you might be applying to very different roles. That's fine—just means less cost savings.

**If you're tracking budget:**
Use the "Total Spent (This Month)" metric. Most users spend $2-5/month generating 10-20 resumes.

**If you're debugging:**
Look at the Pattern History. If you see patterns with high confidence but low usage, it means jSeeker learned a good pattern but hasn't encountered similar jobs since. That's not a problem—it's just waiting.

---

## Bottom Line

**The Learning Insights page proves jSeeker is learning.**

You should see:
1. Pattern library growing over time
2. Cache hit rate increasing
3. Cost per resume decreasing
4. Total savings accumulating

If you're not seeing that after 20-30 resumes, reach out for help. But for most users, the system works automatically—you just watch the numbers improve.

---

**💡 Pro Tip:** Generate resumes in batches for similar roles to maximize pattern reuse. If you apply to 10 "Senior Software Engineer" jobs in a row, jSeeker will learn those patterns fast. If you bounce between "Engineer," "Manager," and "Analyst," learning will be slower (but still works).
